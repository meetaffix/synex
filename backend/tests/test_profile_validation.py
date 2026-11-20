"""Profile and password changes are checked by the server, whatever the browser sent: the browser's checks are only a convenience."""
import atexit
import os
import tempfile
import unittest

TEMP = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = "sqlite:///" + TEMP.name.replace("\\", "/") + "/test.db"
os.environ["SECRET_KEY"] = "test-secret-not-for-production-0123456789"
os.environ["ENCRYPTION_KEY"] = "test-encryption-not-for-production-0123456789"
os.environ["AUTH_PROVIDER"] = "local"
import safety
safety.assert_isolated_database(os.environ["DATABASE_URL"])
from fastapi.testclient import TestClient
from app.database import Base, engine as db_engine
from app.main import app, _attempts
from app.migrations import migrate

atexit.register(db_engine.dispose)
ORIGIN = {"Origin": "http://localhost:5173"}
PASSWORD = "Strong-Test-Password!"


class ProfileValidationTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(db_engine)
        migrate()
        _attempts.clear()
        self.client = TestClient(app, headers=ORIGIN)
        self.addCleanup(self.client.close)
        r = self.client.post("/auth", json={"action": "register", "email": "owner@example.com", "fullName": "Olive Owner", "password": PASSWORD})
        self.assertEqual(r.status_code, 200, r.text)

    def put(self, **body):
        return self.client.put("/auth/me", json=body)

    def test_a_name_must_have_text_and_a_sensible_length(self):
        for bad in ("", "   ", "x" * 121):
            self.assertEqual(self.put(fullName=bad).status_code, 422, repr(bad[:5]))
        r = self.put(fullName="  Ada Lovelace  ")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["fullName"], "Ada Lovelace")

    def test_phone_company_and_title_have_limits(self):
        self.assertEqual(self.put(phone="not a phone").status_code, 422)
        self.assertEqual(self.put(phone="1" * 41).status_code, 422)
        self.assertEqual(self.put(company="c" * 161).status_code, 422)
        self.assertEqual(self.put(designation="d" * 121).status_code, 422)
        ok = self.put(phone="+91 98765-43210", company="Affix", designation="Founder")
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(ok.json()["phone"], "+91 98765-43210")

    def test_a_picture_must_be_a_web_address_not_a_script(self):
        for bad in ("javascript:alert(1)", "data:text/html;base64,AAAA", "ftp://x/y.png", "https://" + "a" * 2100):
            self.assertEqual(self.put(avatarUrl=bad).status_code, 422, bad[:20])
        self.assertEqual(self.put(avatarUrl="https://cdn.example.com/me.png").status_code, 200)

    def test_nobody_can_promote_themselves_or_change_the_plan_through_the_profile(self):
        r = self.put(fullName="Olive Owner", role="admin", plan="scale")
        self.assertEqual(r.status_code, 200, r.text)
        me = self.client.get("/auth/me").json()
        self.assertEqual(me["plan"], "free")
        self.assertNotEqual((me["role"] or "").lower(), "admin")

    def test_a_new_password_is_checked_for_length_and_the_old_one_for_correctness(self):
        change = lambda current, new: self.client.post("/settings", json={"action": "change-password", "currentPassword": current, "newPassword": new})
        self.assertEqual(change("wrong-password", "Another-Strong-Pass1").status_code, 400)
        self.assertEqual(change(PASSWORD, "short").status_code, 400)
        self.assertEqual(change(PASSWORD, "x" * 257).status_code, 400)
        self.assertEqual(change(PASSWORD, PASSWORD).status_code, 400)  # the same password is not a change
        self.assertEqual(change(PASSWORD, "Another-Strong-Pass1").status_code, 200)


if __name__ == "__main__":
    unittest.main()
