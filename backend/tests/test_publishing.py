"""Isolated integration tests. No real LinkedIn/AI calls or user database writes."""
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, Mock
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor

TEMP = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = "sqlite:///" + TEMP.name.replace("\\", "/") + "/test.db"
os.environ["SECRET_KEY"] = "test-secret-not-for-production-0123456789"
os.environ["AUTH_PROVIDER"] = "local"  # tests use the built-in sign-in whatever backend/.env says
os.environ.setdefault("DEEPGRAM_API_KEY", "dg-SENTINEL-never-leak-9f3a7c")  # never the real key from backend/.env
os.environ["ENCRYPTION_KEY"] = "test-encryption-not-for-production-0123456789"
os.environ["LINKEDIN_CLIENT_ID"] = "test-client"
os.environ["LINKEDIN_CLIENT_SECRET"] = "test-client-secret"
import safety
safety.assert_isolated_database(os.environ["DATABASE_URL"])
from fastapi.testclient import TestClient
from app.main import app, _attempts
from app.database import Base, engine, SessionLocal
from app import models
from app.publishing_models import Connection, Post, Execution, OAuthState, SessionToken
from app.security import encrypt_secret
from app.publishing_worker import tick
from app.migrations import migrate

ORIGIN = {"Origin": "http://localhost:5173"}


class PublishingTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(engine)
        migrate()
        _attempts.clear()
        self.client = TestClient(app, headers=ORIGIN)
        self.addCleanup(self.client.close)
        self.user = self.register(self.client, "owner@example.com")
        self.account = self.connection(self.user["id"])

    def register(self, client, email):
        r = client.post("/auth", json={"action": "register", "email": email, "fullName": "Test Writer", "password": "Strong-Test-Password!"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("HttpOnly", r.headers["set-cookie"])
        self.assertNotIn("access_token", r.text)
        return r.json()["user"]

    def connection(self, user_id, scopes=None):
        with SessionLocal() as db:
            a = Connection(user_id=user_id, subject="member123", name="Test Member", access_token=encrypt_secret("mock-token"),
                           expires_at=datetime.now(timezone.utc)+timedelta(days=1), scopes=scopes if scopes is not None else ["openid", "profile", "w_member_social"])
            db.add(a); db.commit(); return a.id

    def draft(self, account=None):
        r = self.client.post("/publishing/posts", json={"title":"Test post", "body":"A real draft stored in the test database.", "accountId":account or self.account})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def action(self, post, action="publish", **extra):
        return self.client.post(f"/publishing/posts/{post['id']}/action", json={"action":action,"version":post["version"],**extra})

    def worker(self, status=201, headers=None, error=None):
        provider=Mock()
        if error: provider.post.side_effect=error
        else: provider.post.return_value=Mock(status_code=status, headers=headers or {"x-restli-id":"urn:li:share:123"})
        with SessionLocal() as db: tick(db, provider)
        return provider

    def test_complete_publishing_journey(self):
        draft=self.draft(); queued=self.action(draft).json()
        self.assertEqual(queued["status"],"scheduled")
        provider=self.worker()
        self.assertEqual(provider.post.call_count,1)
        p=self.client.get("/publishing/posts").json()[0]
        self.assertEqual(p["status"],"published"); self.assertEqual(p["linkedinId"],"urn:li:share:123")
        self.assertEqual(self.worker().post.call_count,0)
        self.assertGreaterEqual(len(self.client.get("/publishing/activity").json()),4)
        self.assertEqual(self.client.get("/publishing/metrics").json()["successRate"],100.0)

    def test_ownership_and_workspace_roles(self):
        other=TestClient(app,headers=ORIGIN); self.addCleanup(other.close)
        user=self.register(other,"other@example.com"); draft=self.draft()
        self.assertEqual(other.get("/publishing/posts").json(),[])
        self.assertEqual(other.put(f"/publishing/posts/{draft['id']}",json={"body":"stolen"}).status_code,404)
        self.assertEqual(other.post(f"/linkedin/accounts/{self.account}/disconnect").status_code,404)
        self.assertEqual(other.post("/publishing/posts",json={"accountId":self.account}).status_code,404)
        with SessionLocal() as db:
            db.add(models.TeamMember(owner_id=self.user["id"],member_id=user["id"],email=user["email"],role="member",status="active"));db.commit()
        self.assertEqual(len(other.get("/publishing/posts").json()),1)
        self.assertEqual(other.post("/publishing/posts",json={"body":"denied"}).status_code,403)
        self.assertEqual(other.get("/publishing/diagnostics").status_code,403)

    def test_optimistic_concurrency_and_schedule_validation(self):
        p=self.draft()
        for date in ["2020-01-01T12:00:00Z", "2099-01-01T12:00:00"]:
            self.assertEqual(self.action(p,"schedule",scheduledAt=date).status_code,422)
        self.assertEqual(self.action(p,"schedule",scheduledAt="2099-01-01T12:00:00Z",timezone="invalid-zone").status_code,422)
        r=self.action(p,"schedule",scheduledAt="2099-01-01T12:00:00+01:00",timezone="Europe/Amsterdam")
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()["scheduledAt"],"2099-01-01T11:00:00+00:00")
        self.assertEqual(self.action(p).status_code,409)
        self.assertEqual(self.client.put(f"/publishing/posts/{p['id']}",json={"version":r.json()["version"],"body":"cannot edit scheduled"}).status_code,409)
        self.assertEqual(self.action(r.json(),"pause").json()["status"],"paused")

    def test_disconnect_removes_credentials_and_pauses(self):
        self.action(self.draft())
        r=self.client.post(f"/linkedin/accounts/{self.account}/disconnect")
        self.assertEqual(r.status_code,200)
        self.assertNotIn("mock-token",r.text)
        with SessionLocal() as db:
            self.assertIsNone(db.get(Connection,self.account).access_token)
            self.assertEqual(db.query(Post).one().status,"paused")
        self.assertEqual(self.worker().post.call_count,0)

    def test_scope_and_expiry_gates(self):
        with SessionLocal() as db:
            a=db.get(Connection,self.account);a.scopes=["openid","profile"];db.commit()
        p=self.draft();self.assertEqual(self.action(p).status_code,403)
        with SessionLocal() as db:
            a=db.get(Connection,self.account);a.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
        self.assertEqual(self.action(p).status_code,409)
        self.assertEqual(self.client.get("/linkedin/accounts").json()[0]["status"],"reconnect_required")

    def test_rate_limit_retry_is_bounded(self):
        self.action(self.draft())
        for attempt in range(4):
            with SessionLocal() as db:
                p=db.query(Post).one();p.scheduled_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
            self.worker(429,{"retry-after":"120"})
        with SessionLocal() as db:
            p=db.query(Post).one();self.assertEqual(p.status,"failed");self.assertEqual(p.attempts,4)

    def test_ambiguous_delivery_not_retried(self):
        import httpx
        self.action(self.draft());self.worker(error=httpx.ReadTimeout("test timeout"))
        p=self.client.get("/publishing/posts").json()[0]
        self.assertEqual(p["status"],"needs_review")
        self.assertEqual(self.action(p).status_code,409)
        self.assertEqual(self.worker().post.call_count,0)

    def test_missing_post_id_is_not_success(self):
        self.action(self.draft());self.worker(201,{"other":"header"})
        self.assertEqual(self.client.get("/publishing/posts").json()[0]["status"],"needs_review")

    def test_restart_recovery_does_not_duplicate(self):
        p=self.draft()
        with SessionLocal() as db:
            row=db.get(Post,p["id"]);row.status="publishing";row.claimed_at=datetime.now(timezone.utc)-timedelta(minutes=6);db.commit()
        self.assertEqual(self.worker().post.call_count,0)
        self.assertEqual(self.client.get("/publishing/posts").json()[0]["status"],"needs_review")

    def test_concurrent_workers_claim_once(self):
        self.action(self.draft()); provider=Mock();provider.post.return_value=Mock(status_code=201,headers={"x-restli-id":"urn:li:share:123"})
        def run():
            with SessionLocal() as db: tick(db,provider)
        # Precreate heartbeat so this tests job claims, not process identity insertion.
        self.worker()
        with SessionLocal() as db:
            p=db.query(Post).one();p.status="scheduled";p.linkedin_id=None;db.commit()
        with ThreadPoolExecutor(2) as executor: list(executor.map(lambda _:run(),range(2)))
        self.assertEqual(provider.post.call_count,1)

    def test_oauth_state_binding_replay_and_persistence(self):
        r=self.client.post("/linkedin/connect");self.assertEqual(r.status_code,200,r.text)
        state=parse_qs(urlparse(r.json()["url"]).query)["state"][0]
        attacker=TestClient(app,headers=ORIGIN);self.addCleanup(attacker.close)
        self.assertEqual(attacker.get("/linkedin/callback",params={"state":state,"code":"test"}).status_code,400)
        with patch("app.linkedin.exchange",return_value=({"access_token":"new-secret","expires_in":3600,"scope":"openid profile w_member_social"},{"sub":"member123","name":"Verified Profile"})):
            r=self.client.get("/linkedin/callback",params={"state":state,"code":"test"},follow_redirects=False)
        self.assertEqual(r.status_code,303);self.assertIn("linkedin=connected",r.headers["location"])
        self.assertEqual(self.client.get("/linkedin/callback",params={"state":state,"code":"test"}).status_code,400)
        with SessionLocal() as db:
            a=db.query(Connection).one();self.assertNotIn("new-secret",a.access_token);self.assertEqual(a.name,"Verified Profile")

    def test_linkedin_login_separate_from_publishing(self):
        guest=TestClient(app,headers=ORIGIN);self.addCleanup(guest.close)
        r=guest.get("/linkedin/login",follow_redirects=False)
        query=parse_qs(urlparse(r.headers["location"]).query)
        self.assertNotIn("w_member_social",query["scope"][0])
        with patch("app.linkedin.exchange",return_value=({"access_token":"test","expires_in":3600},{"sub":"newidentity","name":"LinkedIn Signin","email":"verified@example.com","email_verified":True})):
            r=guest.get("/linkedin/callback",params={"state":query["state"][0],"code":"test"},follow_redirects=False)
        self.assertIn("/dashboard",r.headers["location"])
        self.assertEqual(guest.get("/auth/me").json()["email"],"verified@example.com")
        self.assertEqual(guest.get("/linkedin/accounts").json(),[])

    def test_linkedin_login_does_not_take_over_existing_email(self):
        guest=TestClient(app,headers=ORIGIN);self.addCleanup(guest.close)
        r=guest.get("/linkedin/login",follow_redirects=False);state=parse_qs(urlparse(r.headers["location"]).query)["state"][0]
        with patch("app.linkedin.exchange",return_value=({"access_token":"test","expires_in":3600},{"sub":"different","name":"Other","email":"owner@example.com","email_verified":True})):
            r=guest.get("/linkedin/callback",params={"state":state,"code":"test"},follow_redirects=False)
        self.assertIn("link_existing",r.headers["location"])
        self.assertEqual(guest.get("/auth/me").status_code,401)

    def test_csrf_session_revocation_and_legacy_blocks(self):
        self.assertEqual(self.client.post("/publishing/posts",json={"body":"bad"},headers={"Origin":"https://evil.example"}).status_code,403)
        old_cookie=self.client.cookies.get("synex_session")
        self.assertEqual(self.client.post("/auth/logout").status_code,200)
        self.client.cookies.set("synex_session",old_cookie)
        self.assertEqual(self.client.get("/auth/me").status_code,401)
        # /linkedin-accounts is no longer a retired path; the legacy POST action gateway no longer exists.
        self.assertEqual(self.client.post("/linkedin-accounts",json={"action":"create"}).status_code,405)

    def test_no_fake_settings_or_unsupported_execution(self):
        for path,body in [("/settings",{"action":"update","twoFactorEnabled":True}),("/leads",{"action":"import","source":"connections"})]:
            self.assertEqual(self.client.post(path,json=body).status_code,409)
        # Composing a new conversation stays blocked.
        self.assertEqual(self.client.post("/conversations",json={"action":"compose"}).status_code,409)
        # Campaign launch and replies are executed by the outreach worker, so the middleware no longer
        # blocks them; they reach their handlers and fail validation there.
        for path,body in [("/conversations",{"action":"reply"}),("/campaigns",{"action":"update","status":"active"})]:
            self.assertNotEqual(self.client.post(path,json=body).status_code,409)

    def test_migration_preserves_business_records_and_is_repeatable(self):
        with SessionLocal() as db:
            db.add(models.Lead(user_id=self.user["id"],first_name="Preserved",last_name="Contact"));db.commit()
        migrate();migrate()
        with SessionLocal() as db:self.assertEqual(db.query(models.Lead).one().first_name,"Preserved")

    def test_draft_survives_new_session(self):
        self.draft();self.client.post("/auth/logout")
        r=self.client.post("/auth",json={"action":"login","email":"owner@example.com","password":"Strong-Test-Password!"})
        self.assertEqual(r.status_code,200);self.assertEqual(len(self.client.get("/publishing/posts").json()),1)

    def test_id_token_signature_claims_nonce_and_profile_binding(self):
        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        from app.linkedin import exchange
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.now(timezone.utc)
        claims = {"iss":"https://www.linkedin.com", "aud":"test-client", "sub":"member123", "iat":now, "exp":now+timedelta(minutes=5), "nonce":"nonce123"}
        client = Mock()
        client.__enter__ = Mock(return_value=client)
        client.__exit__ = Mock(return_value=False)
        client.get.return_value.json.return_value = {"sub":"member123"}
        def token(payload, signing_key=key):
            client.post.return_value.json.return_value = {"access_token":"test", "id_token":jwt.encode(payload, signing_key, algorithm="RS256")}
        with patch("app.linkedin.httpx.Client",return_value=client), patch("app.linkedin.JWKS.get_signing_key_from_jwt",return_value=Mock(key=key.public_key())):
            token(claims)
            self.assertEqual(exchange("code","nonce123")[1]["sub"],"member123")
            with self.assertRaises(ValueError): exchange("code","wrong-nonce")
            for changes in [{"aud":"wrong-client"},{"iss":"https://evil.example"},{"exp":now-timedelta(seconds=10)}]:
                token({**claims,**changes})
                with self.assertRaises(jwt.PyJWTError):exchange("code","nonce123")
            token(claims, rsa.generate_private_key(public_exponent=65537,key_size=2048))
            with self.assertRaises(jwt.PyJWTError):exchange("code","nonce123")
            token(claims);client.get.return_value.json.return_value={"sub":"other-member"}
            with self.assertRaises(ValueError):exchange("code","nonce123")

    def test_password_change_revokes_all_sessions(self):
        r=self.client.post("/settings",json={"action":"change-password","currentPassword":"Strong-Test-Password!","newPassword":"New-Strong-Password!"})
        self.assertEqual(r.status_code,200)
        self.assertEqual(self.client.get("/auth/me").status_code,401)

    def test_publishing_never_grants_platform_sign_in(self):
        profile={"sub":"member123","name":"Publishing Member"}
        token={"access_token":"test","expires_in":3600}
        def finish(path, body):
            url=self.client.post(path,json=body).json()["url"]
            state=parse_qs(urlparse(url).query)["state"][0]
            with patch("app.linkedin.exchange",return_value=(token,profile)):
                return self.client.get("/linkedin/callback",params={"code":"test","state":state},follow_redirects=False)
        finish("/linkedin/connect",{"accountId":self.account})
        self.assertFalse(self.client.get("/linkedin/sign-in-identity").json()["linked"])
        self.assertIn("linkedin=linked",finish("/linkedin/link-sign-in",{}).headers["location"])
        self.assertTrue(self.client.get("/linkedin/sign-in-identity").json()["linked"])
        self.assertEqual(self.client.post("/linkedin/unlink-sign-in",json={"password":"wrong"}).status_code,409)
        self.assertEqual(self.client.post("/linkedin/unlink-sign-in",json={"password":"Strong-Test-Password!"}).status_code,200)
        self.assertFalse(self.client.get("/linkedin/sign-in-identity").json()["linked"])
        profile["sub"]="wrong-member"
        self.assertIn("linkedin=failed",finish("/linkedin/connect",{"accountId":self.account}).headers["location"])

    def test_image_validation_ownership_and_publishing(self):
        import base64
        from PIL import Image
        from io import BytesIO
        p=self.draft();path=f"/publishing/posts/{p['id']}/image"
        self.assertEqual(self.client.put(path,json={"version":p["version"],"data":"not-an-image"}).status_code,422)
        img=BytesIO();Image.new("RGB",(8,8),(38,87,142)).save(img,format="PNG")
        r=self.client.put(path,json={"version":p["version"],"data":base64.b64encode(img.getvalue()).decode()})
        self.assertEqual(r.status_code,200,r.text);self.assertTrue(r.json()["hasImage"])
        self.assertEqual(self.client.get(path).headers["content-type"],"image/png")
        other=TestClient(app,headers=ORIGIN);self.addCleanup(other.close);self.register(other,"imgother@example.com")
        self.assertEqual(other.get(path).status_code,404)
        queued=self.action(r.json()).json();self.assertEqual(queued["status"],"scheduled")
        provider=Mock()
        init=Mock();init.json.return_value={"value":{"image":"urn:li:image:fake","uploadUrl":"https://www.linkedin.com/dms-uploads/test"}}
        provider.post.side_effect=[init,Mock(status_code=201,headers={"x-restli-id":"urn:li:share:photo"})]
        with SessionLocal() as db:tick(db,provider)
        self.assertEqual(provider.put.call_count,1)
        self.assertEqual(provider.post.call_args.kwargs["json"]["content"],{"media":{"id":"urn:li:image:fake"}})
        self.assertEqual(self.client.get("/publishing/posts").json()[0]["linkedinId"],"urn:li:share:photo")

    def test_image_upload_rejects_untrusted_destination(self):
        from app.images import prepare_media
        from app.publishing_models import PostImage
        p=self.draft();sender=Mock()
        sender.post.return_value.json.return_value={"value":{"uploadUrl":"https://attacker.example/dms-uploads/file","image":"urn:li:image:fake"}}
        with SessionLocal() as db:
            db.add(PostImage(post_id=p["id"],data=b"test",content_type="image/png"));db.commit()
            with self.assertRaises(ValueError):prepare_media(db,sender,db.get(Post,p["id"]),"urn:li:person:test",{"Authorization":"Bearer fake"})
        sender.put.assert_not_called()

    def test_manual_contacts_lists_and_templates_persist(self):
        list_r=self.client.post("/lead-lists",json={"action":"create","name":"Manual follow-ups"})
        self.assertEqual(list_r.status_code,200,list_r.text)
        r=self.client.post("/leads",json={"action":"bulk","leads":[{"firstName":"Taylor","lastName":"Smith","company":"Test Company"}],"listIds":[list_r.json()["id"]]})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.client.get("/leads").json()[0]["firstName"],"Taylor")
        r=self.client.post("/templates",json={"action":"create","name":"Follow up","body":"Hello, following up on our conversation.","category":"follow_up"})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(len(self.client.get("/templates").json()),1)


def tearDownModule():
    engine.dispose()
    TEMP.cleanup()


if __name__ == "__main__": unittest.main()
