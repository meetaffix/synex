"""Server-side LinkedIn session tests. Everything runs against a local mock login
site and temporary databases; linkedin.com is never contacted."""
import atexit
import json
import logging
import os
import sqlite3
import tempfile
import time
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

TEMP = tempfile.TemporaryDirectory()
# Same values as test_publishing.py: whichever module is imported first fixes the settings.
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
from app.config import settings
safety.assert_isolated_database(settings.database_url)
from app.migrations import migrate
from app.security import decrypt_secret
from app.linkedin_session import service
from app.linkedin_session.manager import SessionManager
from app.linkedin_session.pages import Site
from app.linkedin_session.ratelimit import connect_limiter, proxy_test_limiter, public_limiter
from mock_linkedin import MOCK_SELECTORS, shared_mock
from mock_proxy import shared_proxy

# Release SQLite file handles before the temp directory is removed at interpreter exit.
atexit.register(engine.dispose)

ORIGIN = {"Origin": "http://localhost:5173"}
MOCK = shared_mock()
PROXY = shared_proxy()
PASSWORD, CODE = MOCK.password, MOCK.code
ACCOUNT_KEYS = {"id", "name", "headline", "profileUrl", "avatarUrl", "status", "dailyActionLimit",
                "dailyActionsUsed", "ceilings", "proxyConfigured", "syncMode", "canChangeSyncMode", "pausedReason", "lastCheckedAt", "connectedAt"}




class _Collect(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record):
        self.lines.append(self.format(record))


@contextmanager
def captured_logs():
    """Everything logged anywhere in the process while the block runs, formatted the way a log file would be."""
    handler = _Collect()
    handler.setFormatter(logging.Formatter("%(name)s %(message)s"))
    root = logging.getLogger()
    previous = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield handler.lines
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)


SECRET_TEXT = ("password=Hunter2-Marker cookie=li_at=COOKIE-Marker storage={\"cookies\":[{\"value\":\"STATE-Marker\"}]} "
               "body=Dear-BODY-Marker proxy=http://user:PROXY-Marker@10.0.0.9:3128 code=731946-Marker")
SECRET_MARKERS = ("Hunter2-Marker", "COOKIE-Marker", "STATE-Marker", "BODY-Marker", "PROXY-Marker", "731946-Marker")


def make_manager(site=None, **overrides) -> SessionManager:
    options = dict(max_browsers=3, attempt_timeout=60, poll_interval=0.1, headless=True) | overrides
    return SessionManager(site or MOCK.site, **options)


class SessionApiCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manager = make_manager()
        app.dependency_overrides[service.get_manager] = lambda: cls.manager

    @classmethod
    def tearDownClass(cls):
        cls.manager.shutdown()
        app.dependency_overrides.pop(service.get_manager, None)

    def setUp(self):
        Base.metadata.drop_all(engine)
        migrate()
        _attempts.clear()
        public_limiter.clear()
        connect_limiter.clear()
        proxy_test_limiter.clear()
        PROXY.require_auth, PROXY.delay, PROXY.raw_body = False, 0.0, None
        MOCK.approved = MOCK.force_logged_out = MOCK.force_restricted = False
        allow_loopback = patch.object(settings, "linkedin_proxy_test_allow_private", True)
        allow_loopback.start()
        self.addCleanup(allow_loopback.stop)
        self.client = self.signed_in_client("owner@example.com")
        self.public = TestClient(app, headers=ORIGIN)
        self.addCleanup(self.public.close)
        self.addCleanup(self.settle)

    def signed_in_client(self, email):
        client = TestClient(app, headers=ORIGIN)
        self.addCleanup(client.close)
        r = client.post("/auth", json={"action": "register", "email": email, "fullName": "Test Owner", "password": "Strong-Test-Password!"})
        self.assertEqual(r.status_code, 200, r.text)
        return client

    def settle(self):
        """Cancel anything still running and wait until every browser is closed."""
        for attempt in list(self.manager._attempts.values()):
            self.manager.cancel(attempt)
        self.wait_for(lambda: self.manager.open_browsers == 0 and not self.manager._active)

    def wait_for(self, condition, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(0.1)
        self.fail("condition not reached in time")

    def poll(self, client, url, until, timeout=45):
        deadline, body = time.monotonic() + timeout, None
        while time.monotonic() < deadline:
            body = client.get(url).json()
            if until(body):
                return body
            time.sleep(0.2)
        self.fail(f"state not reached; last response: {body}")

    def connect(self, client=None, email="ok@example.com", password=PASSWORD, **extra):
        r = (client or self.client).post("/linkedin-accounts/connect", json={"identifier": email, "password": password, **extra})
        self.assertEqual(r.status_code, 202, r.text)
        return r.json()["attemptId"]

    def attempt_url(self, attempt_id):
        return f"/linkedin-accounts/connect/{attempt_id}"

    def connect_and_wait(self, email="ok@example.com", client=None):
        attempt = self.connect(client, email)
        done = self.poll(client or self.client, self.attempt_url(attempt), lambda b: b["state"] in ("succeeded", "failed"))
        self.assertEqual(done["state"], "succeeded", done)
        return done["accountId"]

    def account_row(self, account_id):
        with SessionLocal() as db:
            return db.get(models.LinkedInAccount, account_id)

    def reconnect_token(self, account_id):
        r = self.client.post(f"/linkedin-accounts/{account_id}/reconnect-link")
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["url"].rsplit("/", 1)[1]


class LoginFlowTest(SessionApiCase):
    serial = True  # a concurrency test: run_tests.py runs it alone, never beside other tests
    def test_success_saves_encrypted_session_and_profile(self):
        account_id = self.connect_and_wait("ok@example.com")
        accounts = self.client.get("/linkedin-accounts").json()
        self.assertEqual(len(accounts), 1)
        account = accounts[0]
        self.assertEqual(set(account), ACCOUNT_KEYS)
        self.assertEqual((account["id"], account["status"], account["name"]), (account_id, "connected", "Mock Ok"))
        self.assertEqual(account["headline"], "Engineer at Mock Co")
        self.assertTrue(account["profileUrl"].endswith("/in/ok"))
        self.assertTrue(account["avatarUrl"].endswith("avatar-ok.png"))
        self.assertFalse(account["proxyConfigured"])
        self.assertIsNotNone(account["connectedAt"])
        row = self.account_row(account_id)
        self.assertNotIn("li_at", row.session_state_encrypted)
        self.assertIn("li_at", decrypt_secret(row.session_state_encrypted))
        self.assertEqual(set(row.browser_profile), {"userAgent", "viewport", "locale", "timezoneId"})
        self.wait_for(lambda: self.manager.open_browsers == 0)

    def test_timezone_is_part_of_the_fixed_identity(self):
        attempt = self.connect(email="ok@example.com", timezone="Europe/Amsterdam")
        done = self.poll(self.client, self.attempt_url(attempt), lambda b: b["state"] == "succeeded")
        self.assertEqual(self.account_row(done["accountId"]).browser_profile["timezoneId"], "Europe/Amsterdam")

    def test_connecting_the_same_email_again_updates_the_account(self):
        first = self.connect_and_wait("ok@example.com")
        identity = self.account_row(first).browser_profile
        second = self.connect_and_wait("ok@example.com")
        self.assertEqual(first, second)
        self.assertEqual(self.account_row(second).browser_profile, identity)
        self.assertEqual(len(self.client.get("/linkedin-accounts").json()), 1)

    def test_wrong_password_fails_without_creating_an_account(self):
        attempt = self.connect(password="not-the-password")
        done = self.poll(self.client, self.attempt_url(attempt), lambda b: b["state"] == "failed")
        self.assertEqual(done["error"]["code"], "invalid_credentials")
        self.assertNotIn("accountId", done)
        self.assertEqual(self.client.get("/linkedin-accounts").json(), [])
        self.wait_for(lambda: self.manager.open_browsers == 0)

    def test_code_challenge_with_wrong_then_right_code(self):
        attempt = self.connect(email="code@example.com")
        url = self.attempt_url(attempt)
        waiting = self.poll(self.client, url, lambda b: b["state"] == "awaiting_code")
        self.assertEqual(waiting["challenge"]["type"], "email_code")
        self.assertIn("email", waiting["challenge"]["hint"])
        self.assertNotIn("error", waiting)

        self.assertEqual(self.client.post(url + "/code", json={"code": "000000"}).status_code, 200)
        rejected = self.poll(self.client, url, lambda b: b["state"] == "awaiting_code" and "error" in b)
        self.assertEqual(rejected["error"]["code"], "invalid_credentials")

        self.assertEqual(self.client.post(url + "/code", json={"code": CODE}).status_code, 200)
        done = self.poll(self.client, url, lambda b: b["state"] == "succeeded")
        self.assertIn("accountId", done)
        self.assertNotIn("challenge", done)
        self.wait_for(lambda: self.manager.open_browsers == 0)

    def test_code_is_rejected_when_none_is_expected_or_malformed(self):
        attempt = self.connect(email="code@example.com")
        url = self.attempt_url(attempt)
        self.poll(self.client, url, lambda b: b["state"] == "awaiting_code")
        for bad in ("12", "abcdef", "12345678901"):
            self.assertEqual(self.client.post(url + "/code", json={"code": bad}).status_code, 422)
        self.assertEqual(self.client.post(url + "/code", json={"code": CODE}).status_code, 200)
        self.assertEqual(self.client.post(url + "/code", json={"code": CODE}).status_code, 409)

    def test_too_many_wrong_codes_fail_the_attempt(self):
        attempt = self.connect(email="code@example.com")
        url = self.attempt_url(attempt)
        for _ in range(3):
            self.poll(self.client, url, lambda b: b["state"] in ("awaiting_code", "failed"))
            self.client.post(url + "/code", json={"code": "000000"})
            time.sleep(0.5)
        done = self.poll(self.client, url, lambda b: b["state"] == "failed")
        self.assertEqual(done["error"]["code"], "invalid_credentials")

    def test_app_approval_completes_after_approval(self):
        attempt = self.connect(email="approve@example.com")
        url = self.attempt_url(attempt)
        self.poll(self.client, url, lambda b: b["state"] == "awaiting_app_approval")
        MOCK.approved = True
        done = self.poll(self.client, url, lambda b: b["state"] == "succeeded")
        self.assertIn("accountId", done)

    def test_unknown_checkpoint_asks_for_manual_verification_and_frees_the_slot(self):
        attempt = self.connect(email="checkpoint@example.com")
        done = self.poll(self.client, self.attempt_url(attempt), lambda b: b["state"] == "awaiting_manual_verification")
        self.assertNotIn("accountId", done)
        self.wait_for(lambda: self.manager.open_browsers == 0)
        self.connect(email="checkpoint@example.com")  # not a 409: the finished attempt released its lock

    def test_cancel_closes_the_browser(self):
        attempt = self.connect(email="code@example.com")
        url = self.attempt_url(attempt)
        self.poll(self.client, url, lambda b: b["state"] == "awaiting_code")
        self.assertEqual(self.manager.open_browsers, 1)
        self.assertEqual(self.client.delete(url).status_code, 204)
        done = self.poll(self.client, url, lambda b: b["state"] == "failed")
        self.assertEqual(done["error"]["code"], "cancelled")
        self.wait_for(lambda: self.manager.open_browsers == 0)

    def test_second_concurrent_attempt_for_the_same_account_is_409(self):
        self.connect(email="code@example.com")
        r = self.client.post("/linkedin-accounts/connect", json={"identifier": "code@example.com", "password": PASSWORD})
        self.assertEqual(r.status_code, 409)

    def test_validation_errors_are_422(self):
        for body in ({"identifier": "not-an-email", "password": "x"}, {"identifier": "a@example.com"},
                     {"identifier": "a@example.com", "password": "x", "proxyUrl": "ftp://nope"},
                     {"identifier": "a@example.com", "password": "x", "timezone": "Mars/Base"}):
            self.assertEqual(self.client.post("/linkedin-accounts/connect", json=body).status_code, 422, body)


class IsolatedManagerTest(SessionApiCase):
    @contextmanager
    def using(self, manager):
        app.dependency_overrides[service.get_manager] = lambda: manager
        try:
            yield manager
        finally:
            app.dependency_overrides[service.get_manager] = lambda: type(self).manager
            manager.shutdown()

    def test_attempt_times_out_and_closes_its_browser(self):
        with self.using(make_manager(attempt_timeout=3)) as manager:
            attempt = self.connect(email="slow@example.com")
            done = self.poll(self.client, self.attempt_url(attempt), lambda b: b["state"] == "failed")
            self.assertEqual(done["error"]["code"], "timeout")
            self.wait_for(lambda: manager.open_browsers == 0)

    def test_unreachable_proxy_is_reported_as_proxy_error(self):
        dead = Site("http://login.invalid", MOCK_SELECTORS)
        with self.using(make_manager(dead)) as manager:
            attempt = self.connect(proxyUrl="http://127.0.0.1:9")
            done = self.poll(self.client, self.attempt_url(attempt), lambda b: b["state"] == "failed")
            self.assertEqual(done["error"]["code"], "proxy_error")
            self.wait_for(lambda: manager.open_browsers == 0)

    def test_browser_cap_queues_extra_attempts(self):
        with self.using(make_manager(max_browsers=1)) as manager:
            first = self.connect(email="code@example.com")
            self.poll(self.client, self.attempt_url(first), lambda b: b["state"] == "awaiting_code")
            second = self.connect(email="ok@example.com")
            time.sleep(1.5)
            self.assertEqual(self.client.get(self.attempt_url(second)).json()["state"], "starting")
            self.assertEqual(manager.open_browsers, 1)
            self.client.delete(self.attempt_url(first))
            self.poll(self.client, self.attempt_url(second), lambda b: b["state"] == "succeeded")

    def test_shutdown_closes_running_browsers(self):
        with self.using(make_manager()) as manager:
            attempt = self.connect(email="code@example.com")
            self.poll(self.client, self.attempt_url(attempt), lambda b: b["state"] == "awaiting_code")
            self.assertEqual(manager.open_browsers, 1)
            manager.shutdown()
            self.assertEqual(manager.open_browsers, 0)


class AccountApiTest(SessionApiCase):
    def test_requires_authentication(self):
        for method, path in (("get", "/linkedin-accounts"), ("post", "/linkedin-accounts/connect"),
                             ("get", "/linkedin-accounts/connect/x"), ("post", "/linkedin-accounts/x/check"),
                             ("patch", "/linkedin-accounts/x"), ("delete", "/linkedin-accounts/x"),
                             ("post", "/linkedin-accounts/x/reconnect-link")):
            self.assertEqual(getattr(self.public, method)(path).status_code, 401, (method, path))

    def test_patch_limit_pause_and_proxy(self):
        account_id = self.connect_and_wait()
        url = f"/linkedin-accounts/{account_id}"
        self.assertEqual(self.client.patch(url, json={"dailyActionLimit": 25}).json()["dailyActionLimit"], 25)
        self.assertEqual(self.client.patch(url, json={"paused": True}).json()["status"], "paused")
        self.assertEqual(self.client.patch(url, json={"paused": False}).json()["status"], "connected")
        proxied = self.client.patch(url, json={"proxyUrl": "http://user:hunter2pw@proxy.example:8080"}).json()
        self.assertTrue(proxied["proxyConfigured"])
        stored = self.account_row(account_id).proxy_url_encrypted
        self.assertNotIn("hunter2pw", stored)
        self.assertEqual(decrypt_secret(stored), "http://user:hunter2pw@proxy.example:8080")
        self.assertTrue(self.client.patch(url, json={"dailyActionLimit": 30}).json()["proxyConfigured"])
        self.assertFalse(self.client.patch(url, json={"proxyUrl": None}).json()["proxyConfigured"])
        for bad in ({"dailyActionLimit": -1}, {"dailyActionLimit": 500}, {"proxyUrl": "ftp://x:1"}):
            self.assertEqual(self.client.patch(url, json=bad).status_code, 422, bad)
        over = self.client.patch(url, json={"dailyActionLimit": 201})
        self.assertEqual(over.status_code, 422)
        self.assertIn("200", json.dumps(over.json()))  # the error names the ceiling
        # 0 is a real setting: the account is stopped, and it reads back as 0, never as unlimited.
        stopped = self.client.patch(url, json={"dailyActionLimit": 0}).json()
        self.assertEqual(stopped["dailyActionLimit"], 0)
        self.assertEqual(stopped["ceilings"], {"dailyActions": 200, "connectionRequestsPerDay": 40, "connectionRequestsPerWeek": 150,
                                               "messagesPerDay": 100, "profileVisitsPerDay": 80, "followsPerDay": 50})

    def test_check_detects_connected_logged_out_and_restricted(self):
        account_id = self.connect_and_wait()
        url = f"/linkedin-accounts/{account_id}/check"
        before = self.client.post(url).json()
        self.assertEqual((before["status"], set(before)), ("connected", ACCOUNT_KEYS))
        MOCK.force_logged_out = True
        self.assertEqual(self.client.post(url).json()["status"], "needs_reconnect")
        MOCK.force_logged_out, MOCK.force_restricted = False, True
        self.assertEqual(self.client.post(url).json()["status"], "restricted")
        self.assertIsNotNone(self.client.post(url).json()["lastCheckedAt"])

    def test_check_without_a_session_is_409(self):
        account_id = self.connect_and_wait()
        self.client.delete(f"/linkedin-accounts/{account_id}")
        self.assertEqual(self.client.post(f"/linkedin-accounts/{account_id}/check").status_code, 409)

    def test_delete_wipes_the_session_but_keeps_the_record(self):
        account_id = self.connect_and_wait()
        self.assertEqual(self.client.delete(f"/linkedin-accounts/{account_id}").status_code, 204)
        row = self.account_row(account_id)
        self.assertIsNone(row.session_state_encrypted)
        self.assertEqual(row.name, "Mock Ok")
        listed = self.client.get("/linkedin-accounts").json()
        self.assertEqual([a["status"] for a in listed], ["disconnected"])

    def test_workspace_isolation(self):
        account_id = self.connect_and_wait()
        attempt = self.connect(email="code@example.com")
        other = self.signed_in_client("other@example.com")
        self.assertEqual(other.get("/linkedin-accounts").json(), [])
        for method, path, body in (
                ("post", f"/linkedin-accounts/{account_id}/check", None),
                ("patch", f"/linkedin-accounts/{account_id}", {"paused": True}),
                ("delete", f"/linkedin-accounts/{account_id}", None),
                ("post", f"/linkedin-accounts/{account_id}/reconnect-link", None),
                ("get", self.attempt_url(attempt), None),
                ("post", self.attempt_url(attempt) + "/code", {"code": CODE}),
                ("delete", self.attempt_url(attempt), None)):
            r = getattr(other, method)(path, **({"json": body} if body else {}))
            self.assertEqual(r.status_code, 404, (method, path, r.text))
        self.assertEqual(self.client.get("/linkedin-accounts").json()[0]["status"], "connected")


class ReconnectLinkTest(SessionApiCase):
    def test_link_shape_and_public_info(self):
        account_id = self.connect_and_wait()
        r = self.client.post(f"/linkedin-accounts/{account_id}/reconnect-link").json()
        self.assertEqual(set(r), {"url", "expiresAt"})
        self.assertTrue(r["url"].startswith("http://localhost:5173/reconnect/"))
        info = self.public.get("/reconnect/" + r["url"].rsplit("/", 1)[1])
        self.assertEqual(info.status_code, 200)
        self.assertEqual(set(info.json()), {"accountName", "avatarUrl", "expiresAt"})
        self.assertEqual(info.json()["accountName"], "Mock Ok")
        expires = datetime.fromisoformat(r["expiresAt"])
        self.assertAlmostEqual((expires - datetime.now(timezone.utc)).total_seconds(), 86400, delta=60)
        token = r["url"].rsplit("/", 1)[1]
        self.assertNotIn(token, str(self.account_row(account_id).__dict__))  # only a digest is stored

    def test_reconnect_restores_a_logged_out_account_and_the_link_is_single_use(self):
        account_id = self.connect_and_wait()
        MOCK.force_logged_out = True
        self.assertEqual(self.client.post(f"/linkedin-accounts/{account_id}/check").json()["status"], "needs_reconnect")
        MOCK.force_logged_out = False
        token = self.reconnect_token(account_id)

        r = self.public.post(f"/reconnect/{token}/connect", json={"identifier": "ok@example.com", "password": PASSWORD})
        self.assertEqual(r.status_code, 202, r.text)
        url = f"/reconnect/{token}/connect/{r.json()['attemptId']}"
        done = self.poll(self.public, url, lambda b: b["state"] in ("succeeded", "failed"))
        self.assertEqual((done["state"], done["accountId"]), ("succeeded", account_id))
        self.assertEqual(self.client.get("/linkedin-accounts").json()[0]["status"], "connected")

        self.assertEqual(self.public.get(f"/reconnect/{token}").status_code, 404)
        again = self.public.post(f"/reconnect/{token}/connect", json={"identifier": "ok@example.com", "password": PASSWORD})
        self.assertEqual(again.status_code, 404)
        self.assertEqual(self.public.get(url).json()["state"], "succeeded")  # polling still works after consumption

    def test_expired_token_is_404(self):
        account_id = self.connect_and_wait()
        token = self.reconnect_token(account_id)
        self.assertEqual(self.public.get(f"/reconnect/{token}").status_code, 200)
        with SessionLocal() as db:
            db.get(models.LinkedInAccount, account_id).reconnect_token_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.public.get(f"/reconnect/{token}").status_code, 404)
        self.assertEqual(self.public.post(f"/reconnect/{token}/connect", json={"identifier": "ok@example.com", "password": PASSWORD}).status_code, 404)

    def test_a_new_link_replaces_the_old_one(self):
        account_id = self.connect_and_wait()
        old = self.reconnect_token(account_id)
        new = self.reconnect_token(account_id)
        self.assertEqual(self.public.get(f"/reconnect/{old}").status_code, 404)
        self.assertEqual(self.public.get(f"/reconnect/{new}").status_code, 200)

    def test_wrong_profile_is_rejected_and_the_link_stays_valid(self):
        account_id = self.connect_and_wait()
        token = self.reconnect_token(account_id)
        r = self.public.post(f"/reconnect/{token}/connect", json={"identifier": "someone@example.com", "password": PASSWORD})
        done = self.poll(self.public, f"/reconnect/{token}/connect/{r.json()['attemptId']}", lambda b: b["state"] == "failed")
        self.assertEqual(done["error"]["code"], "unknown")
        self.assertEqual(self.public.get(f"/reconnect/{token}").status_code, 200)
        self.assertEqual(self.client.get("/linkedin-accounts").json()[0]["name"], "Mock Ok")

    def test_attempt_routes_mirror_the_authenticated_ones(self):
        account_id = self.connect_account_with_code()
        token = self.reconnect_token(account_id)
        body = {"identifier": "code@example.com", "password": PASSWORD}
        r = self.public.post(f"/reconnect/{token}/connect", json=body)
        url = f"/reconnect/{token}/connect/{r.json()['attemptId']}"
        self.assertEqual(self.public.post(f"/reconnect/{token}/connect", json=body).status_code, 409)
        waiting = self.poll(self.public, url, lambda b: b["state"] == "awaiting_code")
        self.assertEqual(waiting["challenge"]["type"], "email_code")
        self.assertEqual(self.public.post(url + "/code", json={"code": CODE}).status_code, 200)
        self.poll(self.public, url, lambda b: b["state"] == "succeeded")

        token = self.reconnect_token(account_id)
        r = self.public.post(f"/reconnect/{token}/connect", json=body)
        url = f"/reconnect/{token}/connect/{r.json()['attemptId']}"
        self.poll(self.public, url, lambda b: b["state"] == "awaiting_code")
        self.assertEqual(self.public.delete(url).status_code, 204)
        self.assertEqual(self.poll(self.public, url, lambda b: b["state"] == "failed")["error"]["code"], "cancelled")

    def connect_account_with_code(self):
        attempt = self.connect(email="code@example.com")
        url = self.attempt_url(attempt)
        self.poll(self.client, url, lambda b: b["state"] == "awaiting_code")
        self.client.post(url + "/code", json={"code": CODE})
        return self.poll(self.client, url, lambda b: b["state"] == "succeeded")["accountId"]

    def test_an_attempt_is_not_reachable_with_another_accounts_token(self):
        first = self.connect_and_wait("ok@example.com")
        second = self.connect_and_wait("second@example.com")
        token_a, token_b = self.reconnect_token(first), self.reconnect_token(second)
        r = self.public.post(f"/reconnect/{token_a}/connect", json={"identifier": "ok@example.com", "password": PASSWORD})
        attempt = r.json()["attemptId"]
        self.assertEqual(self.public.get(f"/reconnect/{token_b}/connect/{attempt}").status_code, 404)
        self.assertEqual(self.public.get(f"/reconnect/{token_a}/connect/{attempt}").status_code, 200)

    def test_public_routes_are_rate_limited(self):
        codes = [self.public.get("/reconnect/does-not-exist").status_code for _ in range(125)]
        self.assertEqual(codes[0], 404)
        self.assertEqual(codes[-1], 429)
        public_limiter.clear()
        account_id = self.connect_and_wait()
        token = self.reconnect_token(account_id)
        statuses = {self.public.post(f"/reconnect/{token}/connect", json={"identifier": "bad@example.com", "password": "x"}).status_code
                    for _ in range(12)}
        self.assertIn(429, statuses)


def add_admin(owner_email: str, admin_email: str) -> None:
    """Make `admin_email` (already registered) an active admin of the owner's workspace."""
    with SessionLocal() as db:
        owner = db.query(models.User).filter_by(email=owner_email).one()
        admin = db.query(models.User).filter_by(email=admin_email).one()
        db.add(models.TeamMember(owner_id=owner.id, member_id=admin.id, email=admin_email, role="admin", status="active"))
        db.commit()


class LoginIdentifierTest(SessionApiCase):
    def test_phone_number_login_succeeds_and_is_normalised(self):
        account_id = self.connect_and_wait("+1 (415) 555-0123")
        account = self.client.get("/linkedin-accounts").json()[0]
        self.assertEqual((account["id"], account["status"]), (account_id, "connected"))
        self.assertTrue(account["profileUrl"].endswith("/in/phone14155550123"))
        row = self.account_row(account_id)
        self.assertEqual(row.login_identifier, "+14155550123")
        self.assertIsNone(row.email)

    def test_connecting_the_same_phone_again_updates_the_account(self):
        first = self.connect_and_wait("+14155550123")
        self.assertEqual(self.connect_and_wait("+1 415 555 0123"), first)
        self.assertEqual(len(self.client.get("/linkedin-accounts").json()), 1)

    def test_phone_numbers_work_on_the_public_reconnect_route(self):
        account_id = self.connect_and_wait("+14155550123")
        token = self.reconnect_token(account_id)
        r = self.public.post(f"/reconnect/{token}/connect", json={"identifier": "+14155550123", "password": PASSWORD})
        self.assertEqual(r.status_code, 202, r.text)
        done = self.poll(self.public, f"/reconnect/{token}/connect/{r.json()['attemptId']}", lambda b: b["state"] in ("succeeded", "failed"))
        self.assertEqual(done["state"], "succeeded")

    def test_invalid_identifiers_are_422_with_a_helpful_message(self):
        for bad in ("abc", "12345678", "+12", "+0123456789", "a@", "+1415555012345678"):
            r = self.client.post("/linkedin-accounts/connect", json={"identifier": bad, "password": "x"})
            self.assertEqual(r.status_code, 422, bad)
            self.assertIn("phone number with country code", r.text)
            r = self.public.post("/reconnect/x/connect", json={"identifier": bad, "password": "x"})
            self.assertEqual(r.status_code, 422, bad)

    def test_email_is_still_accepted_as_a_deprecated_alias(self):
        r = self.client.post("/linkedin-accounts/connect", json={"email": "Ok@Example.com", "password": PASSWORD})
        self.assertEqual(r.status_code, 202, r.text)
        done = self.poll(self.client, self.attempt_url(r.json()["attemptId"]), lambda b: b["state"] in ("succeeded", "failed"))
        self.assertEqual(self.account_row(done["accountId"]).login_identifier, "ok@example.com")


class SyncPreferenceTest(SessionApiCase):
    def setUp(self):
        super().setUp()
        self.admin = self.signed_in_client("admin@example.com")
        add_admin("owner@example.com", "admin@example.com")

    def connect_with_sync(self, client, identifier, sync_mode=None):
        extra = {"syncMode": sync_mode} if sync_mode else {}
        attempt = self.connect(client, identifier, **extra)
        done = self.poll(client, self.attempt_url(attempt), lambda b: b["state"] in ("succeeded", "failed"))
        self.assertEqual(done["state"], "succeeded", done)
        return done["accountId"]

    def listed(self, client):
        return {a["id"]: a for a in client.get("/linkedin-accounts").json()}

    def test_default_is_synex_only_and_all_can_be_chosen_at_connect(self):
        private = self.connect_with_sync(self.client, "ok@example.com")
        everything = self.connect_with_sync(self.client, "second@example.com", "all")
        accounts = self.listed(self.client)
        self.assertEqual((accounts[private]["syncMode"], accounts[everything]["syncMode"]), ("synex_only", "all"))
        self.assertEqual(self.account_row(private).sync_mode, "synex_only")

    def test_only_the_connecting_member_can_change_it(self):
        account_id = self.connect_with_sync(self.client, "ok@example.com")
        url = f"/linkedin-accounts/{account_id}"
        as_admin = self.listed(self.admin)[account_id]
        self.assertFalse(as_admin["canChangeSyncMode"])
        self.assertTrue(self.listed(self.client)[account_id]["canChangeSyncMode"])
        self.assertEqual(self.admin.patch(url, json={"syncMode": "all"}).status_code, 403)
        self.assertEqual(self.account_row(account_id).sync_mode, "synex_only")
        changed = self.client.patch(url, json={"syncMode": "all"})
        self.assertEqual((changed.status_code, changed.json()["syncMode"]), (200, "all"))
        self.assertEqual(self.account_row(account_id).sync_mode, "all")

    def test_an_admin_who_connected_the_account_owns_the_preference(self):
        account_id = self.connect_with_sync(self.admin, "ok@example.com")
        self.assertIsNotNone(self.account_row(account_id).connected_by_user_id)
        url = f"/linkedin-accounts/{account_id}"
        self.assertEqual(self.client.patch(url, json={"syncMode": "all"}).status_code, 403)
        self.assertEqual(self.admin.patch(url, json={"syncMode": "all"}).json()["syncMode"], "all")
        self.assertFalse(self.listed(self.client)[account_id]["canChangeSyncMode"])

    def test_setting_the_same_value_is_allowed_for_anyone_with_access(self):
        account_id = self.connect_with_sync(self.client, "ok@example.com")
        self.assertEqual(self.admin.patch(f"/linkedin-accounts/{account_id}", json={"syncMode": "synex_only", "dailyActionLimit": 20}).status_code, 200)

    def test_changing_it_through_a_reconnect_of_someone_elses_account_is_403(self):
        account_id = self.connect_with_sync(self.client, "ok@example.com")
        r = self.admin.post("/linkedin-accounts/connect", json={"identifier": "ok@example.com", "password": PASSWORD, "syncMode": "all"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.account_row(account_id).sync_mode, "synex_only")

    def test_reconnecting_keeps_the_preference_and_the_original_owner(self):
        account_id = self.connect_with_sync(self.client, "ok@example.com", "all")
        owner = self.account_row(account_id).connected_by_user_id
        self.connect_with_sync(self.admin, "ok@example.com")
        row = self.account_row(account_id)
        self.assertEqual((row.sync_mode, row.connected_by_user_id), ("all", owner))

    def test_the_reconnect_link_can_change_it(self):
        account_id = self.connect_with_sync(self.client, "ok@example.com")
        token = self.reconnect_token(account_id)
        r = self.public.post(f"/reconnect/{token}/connect", json={"identifier": "ok@example.com", "password": PASSWORD, "syncMode": "all"})
        self.poll(self.public, f"/reconnect/{token}/connect/{r.json()['attemptId']}", lambda b: b["state"] == "succeeded")
        self.assertEqual(self.account_row(account_id).sync_mode, "all")

    def test_invalid_values_are_422(self):
        account_id = self.connect_with_sync(self.client, "ok@example.com")
        self.assertEqual(self.client.patch(f"/linkedin-accounts/{account_id}", json={"syncMode": "everything"}).status_code, 422)
        r = self.client.post("/linkedin-accounts/connect", json={"identifier": "x@example.com", "password": "x", "syncMode": "nope"})
        self.assertEqual(r.status_code, 422)

    def test_legacy_accounts_without_an_owner_fall_back_to_the_workspace_owner(self):
        account_id = self.connect_with_sync(self.client, "ok@example.com")
        with SessionLocal() as db:
            db.get(models.LinkedInAccount, account_id).connected_by_user_id = None
            db.commit()
        url = f"/linkedin-accounts/{account_id}"
        self.assertEqual(self.admin.patch(url, json={"syncMode": "all"}).status_code, 403)
        self.assertEqual(self.client.patch(url, json={"syncMode": "all"}).status_code, 200)


class ProxyTestApiTest(SessionApiCase):
    URL = "/linkedin-accounts/proxy-test"

    def setUp(self):
        super().setUp()
        for target, value in (("linkedin_proxy_test_allow_private", True),
                              ("linkedin_proxy_test_url", "http://ip-echo.example/json"),
                              ("linkedin_proxy_test_timeout_seconds", 10)):
            patcher = patch.object(settings, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_test(self, proxy_url):
        r = self.client.post(self.URL, json={"proxyUrl": proxy_url})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_success_reports_exit_ip_country_and_latency(self):
        result = self.run_test(PROXY.url())
        self.assertTrue(result["ok"])
        self.assertEqual((result["exitIp"], result["country"]), ("203.0.113.7", "NL"))
        self.assertIsInstance(result["latencyMs"], int)
        self.assertNotIn("error", result)

    def test_credentials_are_used_but_never_returned(self):
        PROXY.require_auth = True
        rejected = self.run_test(PROXY.url())
        self.assertEqual((rejected["ok"], rejected["error"]["code"]), (False, "proxy_rejected"))
        accepted = self.run_test(PROXY.url(with_credentials=True))
        self.assertTrue(accepted["ok"])
        wrong = self.run_test(f"http://pxuser:wrong@127.0.0.1:{PROXY.port}")
        self.assertEqual(wrong["error"]["code"], "proxy_rejected")

    def test_unreachable_proxy(self):
        result = self.run_test("http://127.0.0.1:9")
        self.assertEqual((result["ok"], result["error"]["code"]), (False, "proxy_unreachable"))
        self.assertNotIn("latencyMs", result)

    def test_socks5_is_accepted_and_fails_cleanly(self):
        result = self.run_test("socks5://127.0.0.1:9")
        self.assertFalse(result["ok"])
        self.assertIn(result["error"]["code"], ("proxy_unreachable", "proxy_rejected"))

    def test_slow_proxy_times_out(self):
        PROXY.delay = 4
        with patch.object(settings, "linkedin_proxy_test_timeout_seconds", 1):
            started = time.monotonic()
            result = self.run_test(PROXY.url())
        self.assertEqual((result["ok"], result["error"]["code"]), (False, "timeout"))
        self.assertLess(time.monotonic() - started, 3.5)

    def test_unexpected_response_is_bad_response(self):
        for body in ("<html>captive portal</html>", '{"ip": "not-an-ip"}', "{}"):
            PROXY.raw_body = body
            self.assertEqual(self.run_test(PROXY.url())["error"]["code"], "bad_response", body)

    def test_private_proxy_addresses_are_refused_by_default(self):
        with patch.object(settings, "linkedin_proxy_test_allow_private", False):
            result = self.run_test(PROXY.url())
        self.assertEqual(result["error"]["code"], "proxy_not_allowed")

    def test_validation_auth_and_rate_limit(self):
        for bad in ("", "ftp://x:1", "not a url", "http://host"):
            self.assertEqual(self.client.post(self.URL, json={"proxyUrl": bad}).status_code, 422, bad)
        self.assertEqual(self.public.post(self.URL, json={"proxyUrl": PROXY.url()}).status_code, 401)
        statuses = [self.client.post(self.URL, json={"proxyUrl": PROXY.url()}).status_code for _ in range(12)]
        self.assertEqual(statuses[:10], [200] * 10)
        self.assertEqual(statuses[10:], [429, 429])

    def test_proxy_credentials_never_appear_in_responses_or_logs(self):
        secret = PROXY.password
        PROXY.require_auth = True
        responses = []
        with self.assertLogs(level="DEBUG") as logs:
            for url in (f"http://{PROXY.username}:{secret}@127.0.0.1:9", PROXY.url(with_credentials=True),
                        f"http://{PROXY.username}:{secret}@127.0.0.1:{PROXY.port}/", f"socks5://{PROXY.username}:{secret}@127.0.0.1:9"):
                r = self.client.post(self.URL, json={"proxyUrl": url})
                responses.append(r.text)
            PROXY.delay = 3
            with patch.object(settings, "linkedin_proxy_test_timeout_seconds", 1):
                responses.append(self.client.post(self.URL, json={"proxyUrl": PROXY.url(with_credentials=True)}).text)
            logged = "\n".join(logs.output)
        self.assertIn("linkedin proxy test failed", logged)
        for text in responses + [logged]:
            self.assertNotIn(secret, text)
            self.assertNotIn(PROXY.username, text)

    def test_patch_still_stores_the_proxy_encrypted(self):
        account_id = self.connect_and_wait()
        self.client.patch(f"/linkedin-accounts/{account_id}", json={"proxyUrl": PROXY.url(with_credentials=True)})
        self.assertNotIn(PROXY.password, self.account_row(account_id).proxy_url_encrypted)


class HardeningTest(SessionApiCase):
    def token_for(self, account_id):
        return self.reconnect_token(account_id)

    # ---- A1: validation errors never echo the request ------------------------------------------------------
    def test_validation_errors_never_echo_what_was_sent(self):
        secret = "Hunter2-Marker-Password"
        account_id = self.connect_and_wait()
        token = self.token_for(account_id)
        attempts = [
            (self.client, "/linkedin-accounts/connect", {"identifier": "not-an-identifier", "password": secret}),
            (self.client, "/linkedin-accounts/connect", {"email": "bad", "password": secret, "proxyUrl": "ftp://" + secret}),
            (self.public, f"/reconnect/{token}/connect", {"identifier": "also bad", "password": secret}),
            (self.public, "/reconnect/anything/connect", {"identifier": "bad", "password": secret, "syncMode": secret}),
            (self.public, "/auth", {"action": "register", "email": "bad", "fullName": "x", "password": secret}),
        ]
        with captured_logs() as lines:
            for client, path, body in attempts:
                r = client.post(path, json=body)
                self.assertEqual(r.status_code, 422, (path, r.text))
                self.assertNotIn(secret, r.text, path)
                self.assertTrue(all("input" not in item and "ctx" not in item for item in r.json()["detail"]), r.text)
            code = self.client.post(f"/linkedin-accounts/connect/anything/code", json={"code": "ab" + secret})
            self.assertEqual(code.status_code, 422)
            self.assertNotIn(secret, code.text)
        self.assertNotIn(secret, "\n".join(lines))

    # ---- A2: failures are logged by type, never by message --------------------------------------------------
    def test_a_login_failure_with_secrets_in_its_message_is_logged_cleanly(self):
        with captured_logs() as lines, patch.object(MOCK.site, "open_login", side_effect=RuntimeError(SECRET_TEXT)):
            attempt = self.connect(email="ok@example.com")
            done = self.poll(self.client, self.attempt_url(attempt), lambda b: b["state"] == "failed")
        logged = "\n".join(lines)
        self.assertEqual(done["error"]["code"], "unknown")
        self.assertIn("RuntimeError", logged)
        for marker in SECRET_MARKERS:
            self.assertNotIn(marker, logged)
            self.assertNotIn(marker, str(done))

    def test_a_proxy_test_failure_with_secrets_in_its_message_is_logged_cleanly(self):
        with captured_logs() as lines, patch("app.linkedin_session.proxytest._request", side_effect=RuntimeError(SECRET_TEXT)):
            r = self.client.post("/linkedin-accounts/proxy-test", json={"proxyUrl": PROXY.url(with_credentials=True)})
        self.assertEqual(r.json()["error"]["code"], "unknown")
        for marker in SECRET_MARKERS:
            self.assertNotIn(marker, "\n".join(lines))
            self.assertNotIn(marker, r.text)

    def test_the_failure_logger_records_type_and_call_site_but_no_message(self):
        from app.logsafe import log_failure

        def deep():
            raise ValueError(SECRET_TEXT)

        try:
            deep()
        except ValueError as exc:
            with captured_logs() as lines:
                log_failure(logging.getLogger("synex.test"), "something failed", exc)
        logged = "\n".join(lines)
        self.assertIn("ValueError", logged)
        self.assertIn("deep", logged)
        for marker in SECRET_MARKERS:
            self.assertNotIn(marker, logged)

    # ---- A3: private and loopback proxies are refused everywhere a proxy is accepted ----------------------
    def test_private_proxy_addresses_are_refused_on_connect_and_patch(self):
        account_id = self.connect_and_wait()
        with patch.object(settings, "linkedin_proxy_test_allow_private", False):
            for address in ("http://127.0.0.1:8080", "http://user:pw-Marker@10.1.2.3:3128", "socks5://192.168.0.9:1080", "http://localhost:3128"):
                connect = self.client.post("/linkedin-accounts/connect", json={"identifier": "new@example.com", "password": PASSWORD, "proxyUrl": address})
                patch_r = self.client.patch(f"/linkedin-accounts/{account_id}", json={"proxyUrl": address})
                for r in (connect, patch_r):
                    self.assertEqual(r.status_code, 422, (address, r.text))
                    self.assertEqual(r.json()["detail"][0]["type"], "proxy.not_allowed")
                    self.assertNotIn("Marker", r.text)
            self.assertFalse(self.account_row(account_id).proxy_url_encrypted)
            self.assertEqual(len(self.client.get("/linkedin-accounts").json()), 1)  # nothing was started

    def test_a_public_proxy_address_is_accepted_when_the_guard_is_on(self):
        account_id = self.connect_and_wait()
        with patch.object(settings, "linkedin_proxy_test_allow_private", False), patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 0))]):
            r = self.client.patch(f"/linkedin-accounts/{account_id}", json={"proxyUrl": "http://proxy.example.org:3128"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["proxyConfigured"])

    # ---- A4: a reconnect link dies after five failed sign-ins ---------------------------------------------
    def fail_through_link(self, token):
        r = self.public.post(f"/reconnect/{token}/connect", json={"identifier": "ok@example.com", "password": "wrong-password"})
        self.assertEqual(r.status_code, 202, r.text)
        self.poll(self.public, f"/reconnect/{token}/connect/{r.json()['attemptId']}", lambda b: b["state"] == "failed")
        self.wait_for(lambda: not self.manager._active)

    def test_a_reconnect_link_is_invalidated_after_five_failed_attempts(self):
        account_id = self.connect_and_wait()
        token = self.token_for(account_id)
        for count in range(1, 5):
            self.fail_through_link(token)
            self.wait_for(lambda: self.account_row(account_id).reconnect_token_failures == count)
            self.assertEqual(self.public.get(f"/reconnect/{token}").status_code, 200, count)
        self.fail_through_link(token)
        self.wait_for(lambda: self.public.get(f"/reconnect/{token}").status_code == 404)
        self.assertEqual(self.public.post(f"/reconnect/{token}/connect", json={"identifier": "ok@example.com", "password": PASSWORD}).status_code, 404)
        row = self.account_row(account_id)
        self.assertIsNone(row.reconnect_token_digest)
        # A fresh link starts again from zero.
        fresh = self.token_for(account_id)
        self.assertEqual(self.public.get(f"/reconnect/{fresh}").status_code, 200)
        self.assertEqual(self.account_row(account_id).reconnect_token_failures, 0)

    def test_a_cancelled_attempt_does_not_count_against_the_link(self):
        account_id = self.connect_with_code_account()
        token = self.token_for(account_id)
        r = self.public.post(f"/reconnect/{token}/connect", json={"identifier": "code@example.com", "password": PASSWORD})
        url = f"/reconnect/{token}/connect/{r.json()['attemptId']}"
        self.poll(self.public, url, lambda b: b["state"] == "awaiting_code")
        self.assertEqual(self.public.delete(url).status_code, 204)
        self.poll(self.public, url, lambda b: b["state"] == "failed")
        self.wait_for(lambda: not self.manager._active)
        self.assertEqual(self.account_row(account_id).reconnect_token_failures, 0)

    def connect_with_code_account(self):
        attempt = self.connect(email="code@example.com")
        url = self.attempt_url(attempt)
        self.poll(self.client, url, lambda b: b["state"] == "awaiting_code")
        self.client.post(url + "/code", json={"code": CODE})
        return self.poll(self.client, url, lambda b: b["state"] == "succeeded")["accountId"]

    def test_a_successful_sign_in_clears_the_failure_count(self):
        account_id = self.connect_and_wait()
        token = self.token_for(account_id)
        self.fail_through_link(token)
        self.wait_for(lambda: self.account_row(account_id).reconnect_token_failures == 1)
        r = self.public.post(f"/reconnect/{token}/connect", json={"identifier": "ok@example.com", "password": PASSWORD})
        self.poll(self.public, f"/reconnect/{token}/connect/{r.json()['attemptId']}", lambda b: b["state"] == "succeeded")
        self.assertEqual(self.account_row(account_id).reconnect_token_failures, 0)

    # ---- D8: an account's browser identity never changes after its first connect ---------------------------
    def test_connecting_the_same_profile_again_keeps_the_stored_identity(self):
        first = self.connect(email="ok@example.com", timezone="Europe/Amsterdam")
        account_id = self.poll(self.client, self.attempt_url(first), lambda b: b["state"] == "succeeded")["accountId"]
        original = dict(self.account_row(account_id).browser_profile)
        self.assertEqual(original["timezoneId"], "Europe/Amsterdam")

        # A different sign-in name for the same LinkedIn profile, asking for another time zone.
        again = self.connect(email="ok+alias@example.com", timezone="Asia/Tokyo")
        done = self.poll(self.client, self.attempt_url(again), lambda b: b["state"] in ("succeeded", "failed"))
        self.assertEqual(done["state"], "succeeded", done)
        self.assertEqual(done["accountId"], account_id)
        self.assertEqual(len(self.client.get("/linkedin-accounts").json()), 1)
        row = self.account_row(account_id)
        self.assertEqual(dict(row.browser_profile), original)
        self.assertEqual(row.session_status, "connected")
        self.assertEqual(self.client.post(f"/linkedin-accounts/{account_id}/check").json()["status"], "connected")

    def test_reconnecting_the_same_account_keeps_the_stored_identity(self):
        account_id = self.connect_and_wait()
        original = dict(self.account_row(account_id).browser_profile)
        self.connect_and_wait()
        self.assertEqual(dict(self.account_row(account_id).browser_profile), original)


class SecretsTest(SessionApiCase):
    def test_passwords_and_codes_never_reach_logs_or_the_database(self):
        password, code = "Un1que-Passw0rd-Marker", "731946"
        MOCK.password, MOCK.code = password, code
        self.addCleanup(setattr, MOCK, "password", PASSWORD)
        self.addCleanup(setattr, MOCK, "code", CODE)
        with self.assertLogs(level="DEBUG") as logs:
            attempt = self.connect(email="code@example.com", password=password, proxyUrl="http://proxyuser:Pr0xy-Marker@127.0.0.1:9")
            url = self.attempt_url(attempt)
            self.poll(self.client, url, lambda b: b["state"] in ("awaiting_code", "failed"))
            self.client.post(url + "/code", json={"code": code})
            self.poll(self.client, url, lambda b: b["state"] in ("succeeded", "failed"))
            self.wait_for(lambda: self.manager.open_browsers == 0)
            logged = "\n".join(logs.output)
        self.assertIn("linkedin login attempt", logged)
        for secret in (password, code, "Pr0xy-Marker"):
            self.assertNotIn(secret, logged)
        connection = sqlite3.connect(engine.url.database)
        dump = "\n".join(connection.iterdump())
        connection.close()
        for secret in (password, code, "Pr0xy-Marker"):
            self.assertNotIn(secret, dump)


if __name__ == "__main__":
    unittest.main()
