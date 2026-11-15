"""Clerk authentication: tokens are verified with locally generated RSA keys and the Backend API is mocked, so no
test touches Clerk. Covers the happy path, linking by verified email, every way a token can be bad, local mode
staying unchanged, and the webhook signature."""
import atexit
import base64
import hashlib
import hmac
import json
import tempfile
import time
import unittest
from unittest.mock import patch

TEMP = tempfile.TemporaryDirectory()
import os
os.environ["DATABASE_URL"] = "sqlite:///" + TEMP.name.replace("\\", "/") + "/test.db"
os.environ["SECRET_KEY"] = "test-secret-not-for-production-0123456789"
os.environ["AUTH_PROVIDER"] = "local"  # tests use the built-in sign-in whatever backend/.env says
os.environ["ENCRYPTION_KEY"] = "test-encryption-not-for-production-0123456789"
os.environ["LINKEDIN_CLIENT_ID"] = "test-client"
os.environ["LINKEDIN_CLIENT_SECRET"] = "test-client-secret"
os.environ["DEEPGRAM_API_KEY"] = "dg-SENTINEL-never-leak-9f3a7c"
import safety
safety.assert_isolated_database(os.environ["DATABASE_URL"])
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from app import clerk_auth, models
from app.config import settings
safety.assert_isolated_database(settings.database_url)
from app.database import Base, SessionLocal, engine as db_engine
from app.main import app, _attempts
from app.migrations import migrate
from app.security import hash_password

atexit.register(db_engine.dispose)
ORIGIN = {"Origin": "http://localhost:5173"}
HOST = "test-host-42.clerk.accounts.dev"
PUBLISHABLE = "pk_test_" + base64.b64encode(f"{HOST}$".encode()).decode().rstrip("=")
ISSUER = f"https://{HOST}"
PRIVATE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_PRIVATE = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeJwks:
    """Stands in for PyJWKClient: always hands back the test public key."""
    def get_signing_key_from_jwt(self, token):
        return type("Key", (), {"key": PRIVATE.public_key()})()


def token(sub="user_abc", key=PRIVATE, alg="RS256", iss=ISSUER, exp=300, nbf=0, azp="http://localhost:5173", **extra):
    now = int(time.time())
    claims = {"sub": sub, "iss": iss, "iat": now, "exp": now + exp, "nbf": now + nbf, **extra}
    if azp is not None:
        claims["azp"] = azp
    return jwt.encode(claims, key, algorithm=alg)


def clerk_user(email="ada@example.com", status="verified", first="Ada", last="Lovelace", image="https://img.example/a.png"):
    return {"id": "user_abc", "first_name": first, "last_name": last, "image_url": image, "primary_email_address_id": "idn_1",
            "email_addresses": [{"id": "idn_0", "email_address": "old@example.com", "verification": {"status": "verified"}},
                                {"id": "idn_1", "email_address": email, "verification": {"status": status}}]}


class ClerkCase(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(db_engine)
        migrate()
        _attempts.clear()
        for target, value in (("auth_provider", "clerk"), ("clerk_publishable_key", PUBLISHABLE), ("clerk_secret_key", "sk_test_fake"),
                              ("clerk_issuer", ""), ("clerk_webhook_secret", "")):
            patcher = patch.object(settings, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        jwks = patch.object(clerk_auth, "_jwks_client", return_value=FakeJwks())
        jwks.start()
        self.addCleanup(jwks.stop)
        self.lookups: list[str] = []
        self.clerk = {"user_abc": clerk_user()}

        def fake_fetch(clerk_id):
            self.lookups.append(clerk_id)
            if clerk_id not in self.clerk:
                raise clerk_auth.ClerkAuthError("HTTPStatusError")
            return self.clerk[clerk_id]
        fetch = patch.object(clerk_auth, "fetch_clerk_user", side_effect=fake_fetch)
        fetch.start()
        self.addCleanup(fetch.stop)
        self.client = TestClient(app, headers=ORIGIN)
        self.addCleanup(self.client.close)

    def get_me(self, bearer=None, **kw):
        headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
        return self.client.get("/auth/me", headers=headers, **kw)

    def users(self):
        with SessionLocal() as db:
            return db.query(models.User).all()


class IssuerTest(ClerkCase):
    def test_the_issuer_comes_from_the_publishable_key_and_can_be_overridden(self):
        self.assertEqual(clerk_auth.frontend_api_host(), HOST)
        self.assertEqual(clerk_auth.issuer(), ISSUER)
        with patch.object(settings, "clerk_issuer", "https://custom.example.com/"):
            self.assertEqual(clerk_auth.issuer(), "https://custom.example.com")
        with patch.object(settings, "clerk_publishable_key", "not-a-key"), self.assertRaises(clerk_auth.ClerkAuthError):
            clerk_auth.issuer()


class SignInTest(ClerkCase):
    def test_a_first_sign_in_creates_the_user_from_clerk_and_later_requests_do_not_call_clerk(self):
        r = self.get_me(token())
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["email"], r.json()["fullName"]), ("ada@example.com", "Ada Lovelace"))
        self.assertEqual(self.get_me(token()).status_code, 200)
        self.assertEqual(self.lookups, ["user_abc"])  # looked up once, then the link is stored
        (user,) = self.users()
        self.assertEqual(user.clerk_user_id, "user_abc")

    def test_an_existing_user_is_matched_by_verified_email_and_keeps_their_id_and_data(self):
        with SessionLocal() as db:
            old = models.User(email="Ada@Example.com", full_name="Ada Old", hashed_password=hash_password("Old-Password-123!"), company="Engines")
            db.add(old)
            db.flush()
            db.add(models.Template(user_id=old.id, name="Mine", body="Hello"))
            db.commit()
            old_id = old.id
        r = self.get_me(token())
        self.assertEqual((r.status_code, r.json()["id"]), (200, old_id))
        (user,) = self.users()
        self.assertEqual((user.id, user.company, user.clerk_user_id), (old_id, "Engines", "user_abc"))
        with SessionLocal() as db:
            self.assertEqual(db.query(models.Template).filter_by(user_id=old_id).count(), 1)

    def test_an_unverified_email_is_never_linked_or_created(self):
        with SessionLocal() as db:
            db.add(models.User(email="ada@example.com", full_name="Ada", hashed_password=hash_password("Old-Password-123!")))
            db.commit()
        self.clerk["user_abc"] = clerk_user(status="unverified")
        self.assertEqual(self.get_me(token()).status_code, 401)
        (user,) = self.users()
        self.assertIsNone(user.clerk_user_id)
        self.clerk["user_abc"] = clerk_user(email="new@example.com", status="unverified")
        self.assertEqual(self.get_me(token()).status_code, 401)
        self.assertEqual(len(self.users()), 1)

    def test_an_email_already_linked_to_another_clerk_user_is_refused(self):
        with SessionLocal() as db:
            db.add(models.User(email="ada@example.com", full_name="Ada", hashed_password=hash_password("x" * 12), clerk_user_id="user_other"))
            db.commit()
        self.assertEqual(self.get_me(token()).status_code, 401)

    def test_a_clerk_lookup_failure_is_a_plain_401(self):
        r = self.get_me(token(sub="user_unknown"))
        self.assertEqual((r.status_code, r.json()), (401, {"detail": "Not authenticated"}))
        self.assertEqual(self.users(), [])

    def test_team_roles_still_work_for_a_clerk_user(self):
        self.get_me(token())
        self.assertEqual(self.client.get("/campaigns", headers={"Authorization": f"Bearer {token()}"}).status_code, 200)


class BadTokenTest(ClerkCase):
    def test_every_bad_token_is_a_401_with_no_detail(self):
        bad = {
            "none at all": None,
            "expired": token(exp=-60),
            "not yet valid": token(nbf=3600),
            "wrong issuer": token(iss="https://evil.example.com"),
            "signed with another key": token(key=OTHER_PRIVATE),
            "wrong algorithm": jwt.encode({"sub": "user_abc", "iss": ISSUER, "exp": int(time.time()) + 300, "iat": int(time.time())}, "secret-secret-secret-secret-1234", algorithm="HS256"),
            "unauthorized party": token(azp="https://evil.example.com"),
            "garbage": "not.a.jwt",
        }
        for name, value in bad.items():
            with self.subTest(name):
                r = self.get_me(value)
                self.assertEqual((r.status_code, r.json()), (401, {"detail": "Not authenticated"}), name)
        self.assertEqual(self.users(), [])
        self.assertEqual(self.lookups, [])

    def test_an_algorithm_none_token_is_refused(self):
        unsigned = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode() + "." + base64.urlsafe_b64encode(
            json.dumps({"sub": "user_abc", "iss": ISSUER, "exp": int(time.time()) + 300, "iat": int(time.time())}).encode()).rstrip(b"=").decode() + "."
        self.assertEqual(self.get_me(unsigned).status_code, 401)

    def test_in_clerk_mode_the_old_cookie_session_is_not_accepted(self):
        with patch.object(settings, "auth_provider", "local"):
            r = self.client.post("/auth", json={"action": "register", "email": "cookie@example.com", "fullName": "Cookie", "password": "Strong-Test-Password!"})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(self.client.get("/auth/me").status_code, 200)
        self.assertEqual(self.client.get("/auth/me").status_code, 401)  # same cookie, Clerk mode


class LocalModeTest(ClerkCase):
    def test_local_mode_ignores_bearer_tokens_and_keeps_password_sign_in(self):
        with patch.object(settings, "auth_provider", "local"):
            self.assertEqual(self.get_me(token()).status_code, 401)
            r = self.client.post("/auth", json={"action": "register", "email": "pw@example.com", "fullName": "Pw", "password": "Strong-Test-Password!"})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(self.client.get("/auth/me").status_code, 200)
            self.assertEqual(self.client.post("/auth/logout").status_code, 200)
        self.assertEqual(self.lookups, [])


class GatewayTest(ClerkCase):
    def test_password_actions_answer_410_in_clerk_mode_and_logout_is_a_no_op(self):
        for action in ("login", "register", "reset-request", "reset-confirm"):
            r = self.client.post("/auth", json={"action": action, "email": "x@example.com", "password": "Strong-Test-Password!", "fullName": "X"})
            self.assertEqual(r.status_code, 410, action)
        self.assertEqual(self.client.post("/auth/logout").json(), {"ok": True})


SECRET_BYTES = b"clerk-webhook-test-secret-bytes!"
WHSEC = "whsec_" + base64.b64encode(SECRET_BYTES).decode()


def signed(body: dict, msg_id="msg_1", ts=None, key=SECRET_BYTES):
    raw = json.dumps(body).encode()
    ts = str(int(time.time()) if ts is None else ts)
    sig = base64.b64encode(hmac.new(key, f"{msg_id}.{ts}.".encode() + raw, hashlib.sha256).digest()).decode()
    return raw, {"svix-id": msg_id, "svix-timestamp": ts, "svix-signature": f"v1,{sig}", "Content-Type": "application/json"}


class WebhookTest(ClerkCase):
    def setUp(self):
        super().setUp()
        patcher = patch.object(settings, "clerk_webhook_secret", WHSEC)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.get_me(token())  # links user_abc

    def send(self, body, **kw):
        raw, headers = signed(body, **kw)
        return self.client.post("/clerk/webhook", content=raw, headers=headers)

    def test_a_signed_update_changes_the_linked_users_profile_and_is_idempotent(self):
        event = {"type": "user.updated", "data": {**clerk_user(email="ada.new@example.com", first="Ada", last="King"), "id": "user_abc"}}
        for _ in range(2):
            self.assertEqual(self.send(event).status_code, 200)
        (user,) = self.users()
        self.assertEqual((user.full_name, user.email), ("Ada King", "ada.new@example.com"))

    def test_an_email_that_belongs_to_another_user_is_not_taken(self):
        with SessionLocal() as db:
            db.add(models.User(email="taken@example.com", full_name="T", hashed_password=hash_password("x" * 12)))
            db.commit()
        self.send({"type": "user.updated", "data": {**clerk_user(email="taken@example.com"), "id": "user_abc"}})
        with SessionLocal() as db:
            self.assertEqual(db.query(models.User).filter_by(clerk_user_id="user_abc").one().email, "ada@example.com")

    def test_a_delete_only_unlinks_and_keeps_the_data(self):
        self.assertEqual(self.send({"type": "user.deleted", "data": {"id": "user_abc", "deleted": True}}).status_code, 200)
        (user,) = self.users()
        self.assertIsNone(user.clerk_user_id)

    def test_a_bad_signature_a_stale_timestamp_and_missing_headers_are_refused(self):
        event = {"type": "user.updated", "data": {"id": "user_abc", "first_name": "Evil"}}
        raw, headers = signed(event, key=b"another-secret-another-secret-12")
        self.assertEqual(self.client.post("/clerk/webhook", content=raw, headers=headers).status_code, 400)
        self.assertEqual(self.send(event, ts=int(time.time()) - 3600).status_code, 400)
        raw, headers = signed(event)
        self.assertEqual(self.client.post("/clerk/webhook", content=raw + b" ", headers=headers).status_code, 400)  # body changed
        self.assertEqual(self.client.post("/clerk/webhook", content=raw, headers={"Content-Type": "application/json"}).status_code, 400)
        (user,) = self.users()
        self.assertEqual(user.full_name, "Ada Lovelace")

    def test_without_a_signing_secret_the_route_is_off(self):
        with patch.object(settings, "clerk_webhook_secret", ""):
            raw, headers = signed({"type": "user.updated", "data": {}})
            self.assertEqual(self.client.post("/clerk/webhook", content=raw, headers=headers).status_code, 503)


class MigrationTest(ClerkCase):
    def test_the_clerk_link_is_unique_and_the_migration_is_recorded(self):
        from app.publishing_models import Migration
        with SessionLocal() as db:
            self.assertIsNotNone(db.get(Migration, "008_clerk_user_id"))
            db.add(models.User(email="a@example.com", full_name="A", hashed_password="x", clerk_user_id="user_dup"))
            db.commit()
            db.add(models.User(email="b@example.com", full_name="B", hashed_password="x", clerk_user_id="user_dup"))
            with self.assertRaises(Exception):
                db.commit()


PREVIEW = "https://synex-git-feature-x-meetaffix-1903s-projects.vercel.app"
PREVIEW_REGEX = r"https://synex(-[a-z0-9]+)*-meetaffix-1903s-projects\.vercel\.app"


class OriginRegexTest(ClerkCase):
    """Vercel preview deployments are admitted by a project-specific regex, never by a wildcard."""
    def setUp(self):
        super().setUp()
        patcher = patch.object(settings, "cors_origin_regex", PREVIEW_REGEX)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_regex_must_match_the_whole_origin_and_the_listed_origins_still_work(self):
        self.assertTrue(settings.origin_allowed("http://localhost:5173"))
        self.assertTrue(settings.origin_allowed(PREVIEW))
        for bad in ("https://evil.vercel.app", PREVIEW + ".evil.com", "https://x" + PREVIEW[len("https://"):] + "/", "http://" + PREVIEW[len("https://"):], "", None):
            self.assertFalse(settings.origin_allowed(bad), bad)
        with patch.object(settings, "cors_origin_regex", ""):
            self.assertFalse(settings.origin_allowed(PREVIEW))  # off by default

    def test_a_preview_origin_passes_the_write_check_and_cors_but_a_stranger_does_not(self):
        r = self.client.post("/auth", headers={"Origin": PREVIEW}, json={"action": "login", "email": "a@example.com", "password": "x"})
        self.assertNotEqual(r.status_code, 403)
        r = self.client.post("/auth", headers={"Origin": "https://evil.vercel.app"}, json={"action": "login", "email": "a@example.com", "password": "x"})
        self.assertEqual(r.status_code, 403)
        ok = self.client.options("/auth/me", headers={"Origin": PREVIEW, "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"})
        self.assertEqual(ok.headers.get("access-control-allow-origin"), PREVIEW)
        bad = self.client.options("/auth/me", headers={"Origin": "https://evil.vercel.app", "Access-Control-Request-Method": "GET"})
        self.assertIsNone(bad.headers.get("access-control-allow-origin"))

    def test_a_token_issued_to_a_preview_origin_is_accepted_and_a_stranger_is_not(self):
        self.assertEqual(self.get_me(token(azp=PREVIEW)).status_code, 200)
        self.assertEqual(self.get_me(token(azp="https://evil.vercel.app")).status_code, 401)


if __name__ == "__main__":
    unittest.main()
