"""Plan limits live in the database and are enforced by the server: the assistant's monthly minutes cannot be set above the plan's,
a value saved before the limit existed is not honoured, and the browser only displays what the server says."""
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
from app import models
from app.assistant import service
from app.assistant.models import AssistantSettings
from app.database import Base, SessionLocal, engine as db_engine
from app.main import app, _attempts
from app.migrations import migrate

atexit.register(db_engine.dispose)
ORIGIN = {"Origin": "http://localhost:5173"}
PASSWORD = "Strong-Test-Password!"


class PlanLimitTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(db_engine)
        migrate()
        _attempts.clear()
        self.client = TestClient(app, headers=ORIGIN)
        self.addCleanup(self.client.close)
        r = self.client.post("/auth", json={"action": "register", "email": "owner@example.com", "fullName": "Olive Owner", "password": PASSWORD})
        self.assertEqual(r.status_code, 200, r.text)
        self.uid = r.json()["user"]["id"]

    def set_limit(self, plan, minutes):
        with SessionLocal() as db:
            db.get(models.Plan, plan).assistant_minutes = minutes
            db.commit()

    def test_the_three_plans_are_in_the_database_and_free_is_the_default(self):
        with SessionLocal() as db:
            self.assertEqual({p.id for p in db.query(models.Plan)}, {"free", "pro", "scale"})
            self.assertEqual(db.get(models.User, self.uid).plan, "free")
        migrate()  # running it again changes nothing and does not overwrite a value someone edited
        self.set_limit("free", 45)
        migrate()
        with SessionLocal() as db:
            self.assertEqual(db.get(models.Plan, "free").assistant_minutes, 45)

    def test_the_settings_say_what_the_plan_allows_and_it_comes_from_the_database(self):
        self.set_limit("free", 45)
        s = self.client.get("/assistant/settings").json()
        self.assertEqual((s["plan"], s["planMinuteLimit"]), ("free", 45))
        self.assertLessEqual(s["monthlyMinuteCap"], 45)

    def test_a_limit_above_the_plan_is_refused_by_the_server(self):
        free = self.client.get("/assistant/settings").json()["planMinuteLimit"]
        r = self.client.put("/assistant/settings", json={"monthlyMinuteCap": free + 1})
        self.assertEqual(r.status_code, 422, r.text)
        self.assertIn(f"{free}", str(r.json()["detail"]))
        self.assertIn("Free", str(r.json()["detail"]))
        ok = self.client.put("/assistant/settings", json={"monthlyMinuteCap": free})
        self.assertEqual(ok.status_code, 200, ok.text)
        zero = self.client.put("/assistant/settings", json={"monthlyMinuteCap": 0})
        self.assertEqual(zero.status_code, 200, zero.text)

    def test_a_value_saved_above_the_plan_is_not_honoured(self):
        with SessionLocal() as db:
            service.get_settings_row(db, self.uid).monthly_minute_cap = 1000  # as it could be set before the limit existed
            db.commit()
        s = self.client.get("/assistant/settings").json()
        self.assertEqual(s["monthlyMinuteCap"], s["planMinuteLimit"])
        self.assertEqual(s["remainingSeconds"], s["planMinuteLimit"] * 60)

    def test_a_better_plan_raises_the_limit(self):
        before = self.client.get("/assistant/settings").json()["planMinuteLimit"]
        with SessionLocal() as db:
            db.get(models.User, self.uid).plan = "pro"
            db.commit()
        after = self.client.get("/assistant/settings").json()
        self.assertGreater(after["planMinuteLimit"], before)
        self.assertEqual(after["plan"], "pro")

    def test_the_plan_page_reports_plan_limits_usage_and_that_upgrading_is_not_available_yet(self):
        r = self.client.get("/plan")
        self.assertEqual(r.status_code, 200, r.text)
        p = r.json()
        self.assertEqual((p["plan"], p["name"]), ("free", "Free"))
        self.assertEqual(p["limits"]["assistantMinutes"], p["assistantMinutes"]["limit"])
        self.assertEqual(p["assistantMinutes"]["used"], 0)
        self.assertFalse(p["upgradeAvailable"])
        self.assertTrue(p["upgradeNote"])
        self.assertEqual([x["id"] for x in p["plans"]], ["free", "pro", "scale"])


if __name__ == "__main__":
    unittest.main()
