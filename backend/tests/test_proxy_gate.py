"""The hosted safety gate: where REQUIRE_ACCOUNT_PROXY is on, no browser is opened for an account without a proxy. Not for a login,
not for a health check, not for a worker batch. Nothing here contacts linkedin.com."""
import atexit
import os
import tempfile
import time
import unittest
from unittest.mock import patch

TEMP = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = "sqlite:///" + TEMP.name.replace("\\", "/") + "/test.db"
os.environ["SECRET_KEY"] = "test-secret-not-for-production-0123456789"
os.environ["ENCRYPTION_KEY"] = "test-encryption-not-for-production-0123456789"
os.environ["AUTH_PROVIDER"] = "local"
os.environ.setdefault("DEEPGRAM_API_KEY", "dg-SENTINEL-never-leak-9f3a7c")
import safety
safety.assert_isolated_database(os.environ["DATABASE_URL"])
from fastapi import HTTPException
from app import database, models, publishing_models  # noqa: F401
from app.config import settings
from app.database import Base, SessionLocal
from app.linkedin_session import service, store
from app.linkedin_session.manager import CheckFailed, PROXY_REQUIRED_MESSAGE, ProxyRequired, SessionManager
from app.linkedin_session.pages import REAL_SELECTORS, Site

atexit.register(database.engine.dispose)
PASSWORD = "not-a-real-password"


def manager(require: bool) -> SessionManager:
    return SessionManager(Site("https://example.invalid", REAL_SELECTORS), max_browsers=1, attempt_timeout=30, poll_interval=0.1,
                          headless=True, require_proxy=require)


def wait(attempt, seconds=30):
    deadline = time.monotonic() + seconds
    while attempt.active and time.monotonic() < deadline:
        time.sleep(0.1)


class ProxyGateTest(unittest.TestCase):
    def test_a_login_without_a_proxy_is_refused_with_a_clear_message_and_no_browser_is_started(self):
        mgr = manager(True)
        self.addCleanup(mgr.shutdown)
        attempt = mgr.start_login(workspace_id="w", identifier="a@example.com", password=PASSWORD, proxy_url=None,
                                  timezone="Asia/Kolkata", identity=None, target_account_id=None)
        wait(attempt)
        self.assertEqual(attempt.state, "failed")
        self.assertEqual(attempt.error, ("proxy_required", PROXY_REQUIRED_MESSAGE))
        self.assertEqual(mgr.open_browsers, 0)
        self.assertIsNone(mgr._playwright)  # not even the browser driver was started

    def test_a_health_check_and_a_worker_session_without_a_proxy_are_refused_too(self):
        mgr = manager(True)
        self.addCleanup(mgr.shutdown)
        with self.assertRaises(CheckFailed) as caught:
            mgr.check_session(storage_state={"cookies": []}, identity={"userAgent": "x", "viewport": {"width": 1366, "height": 768},
                                                                      "locale": "en-US", "timezoneId": "Asia/Kolkata"}, proxy_url=None)
        self.assertEqual(str(caught.exception), PROXY_REQUIRED_MESSAGE)
        future = mgr.submit_session_work(storage_state={"cookies": []}, identity={"userAgent": "x"}, proxy_url=None,
                                         work=lambda page, context: None)
        with self.assertRaises(ProxyRequired):
            future.result(timeout=20)
        self.assertEqual(mgr.open_browsers, 0)
        self.assertIsNone(mgr._playwright)

    def test_with_a_proxy_the_gate_lets_the_browser_start(self):
        mgr = manager(True)
        self.addCleanup(mgr.shutdown)
        attempt = mgr.start_login(workspace_id="w", identifier="a@example.com", password=PASSWORD, proxy_url="http://127.0.0.1:9",
                                  timezone="Asia/Kolkata", identity=None, target_account_id=None)
        wait(attempt, 60)
        self.assertNotEqual(attempt.error and attempt.error[0], "proxy_required")  # it went on to try the (dead) proxy

    def test_where_the_gate_is_off_a_login_without_a_proxy_is_not_refused(self):
        mgr = manager(False)
        self.addCleanup(mgr.shutdown)
        attempt = mgr.start_login(workspace_id="w", identifier="a@example.com", password=PASSWORD, proxy_url=None,
                                  timezone="Asia/Kolkata", identity=None, target_account_id=None)
        wait(attempt, 60)
        self.assertNotEqual(attempt.error and attempt.error[0], "proxy_required")


class ServiceGateTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(database.engine)
        Base.metadata.create_all(database.engine)
        with SessionLocal() as db:
            user = models.User(email="a@example.com", full_name="A", hashed_password="x")
            db.add(user)
            db.flush()
            account = models.LinkedInAccount(user_id=user.id, name="Acct", daily_action_limit=0, browser_profile={"userAgent": "x"},
                                             session_state_encrypted=store.encrypt_secret('{"cookies": []}') if hasattr(store, "encrypt_secret") else None)
            db.add(account)
            db.commit()
            self.account_id = account.id

    def test_the_check_now_button_gets_a_409_with_the_message_when_the_account_has_no_proxy(self):
        with SessionLocal() as db:
            account = db.get(models.LinkedInAccount, self.account_id)
            with patch.object(settings, "require_account_proxy", True), patch.object(store, "load_state", return_value={"cookies": []}):
                with self.assertRaises(HTTPException) as caught:
                    service.run_check(manager(True), account)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.detail, PROXY_REQUIRED_MESSAGE)


if __name__ == "__main__":
    unittest.main()
