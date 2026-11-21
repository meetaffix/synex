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
from app import plans
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
            self.assertEqual({p.id for p in db.query(models.Plan)}, {"free", "pro", "scale", "enterprise"})
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
        self.assertEqual((p["plan"], p["name"]), ("free", "Demo"))
        self.assertEqual(p["limits"]["assistantMinutes"], p["assistantMinutes"]["limit"])
        self.assertEqual(p["assistantMinutes"]["used"], 0)
        self.assertFalse(p["upgradeAvailable"])
        self.assertTrue(p["upgradeNote"])
        self.assertEqual([x["id"] for x in p["plans"]], ["free", "pro", "scale", "enterprise"])



class SeatsAndSendingLimitsTest(PlanLimitTest):
    """A plan sets how many sender accounts a workspace may hold and how much each may send in a day; Enterprise can be unlocked per customer."""

    def set_plan(self, plan, overrides=None):
        with SessionLocal() as db:
            owner = db.get(models.User, self.uid)
            owner.plan, owner.plan_overrides = plan, overrides
            db.commit()

    def add_account(self):
        with SessionLocal() as db:
            db.add(models.LinkedInAccount(user_id=self.uid, name="Sender", status="active"))
            db.commit()

    def limits(self):
        with SessionLocal() as db:
            return plans.limits_of(db, db.get(models.User, self.uid))

    def test_the_demo_plan_allows_one_account_and_refuses_the_second_on_the_server(self):
        self.assertEqual(self.limits()["seats"], 1)
        self.assertEqual(self.client.post("/linkedin-accounts/invite-link").status_code, 200)  # the one seat
        refused = self.client.post("/linkedin-accounts/invite-link")
        self.assertEqual(refused.status_code, 403, refused.text)
        self.assertIn("Demo plan includes 1 LinkedIn account", refused.json()["detail"])

    def test_the_plans_step_up_and_daily_sending_stays_under_the_hard_ceilings(self):
        seats = {}
        for plan in ("free", "pro", "scale", "enterprise"):
            self.set_plan(plan)
            seats[plan] = self.limits()["seats"]
            self.assertLessEqual(self.limits()["dailyInvites"], 40)
            self.assertLessEqual(self.limits()["dailyMessages"], 100)
            self.assertLessEqual(self.limits()["dailyVisits"], 80)
        self.assertEqual((seats["free"], seats["pro"], seats["scale"]), (1, 15, 30))
        self.assertGreater(seats["enterprise"], 30)

    def test_an_enterprise_override_unlocks_seats_but_never_a_hard_ceiling(self):
        self.set_plan("enterprise", {"seats": 120, "dailyInvites": 500})
        limits = self.limits()
        self.assertEqual(limits["seats"], 120)
        self.assertEqual(limits["dailyInvites"], 40)  # held at the ceiling

    def test_the_plan_page_reports_seats_and_the_daily_sending_each_plan_allows(self):
        self.add_account()
        p = self.client.get("/plan").json()
        self.assertEqual(p["seats"], {"used": 1, "limit": 1})
        demo = next(x for x in p["plans"] if x["id"] == "free")
        self.assertEqual((demo["seats"], demo["dailyInvites"], demo["dailyMessages"]), (1, 10, 20))


if __name__ == "__main__":
    unittest.main()
