"""The accounts overview: seats, each account's 24-hour usage, and acceptance and reply rates from its campaigns' leads."""
import atexit
import os
import tempfile
import unittest

TEMP = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = "sqlite:///" + TEMP.name.replace("\\", "/") + "/test.db"
os.environ["SECRET_KEY"] = "test-secret-not-for-production-0123456789"
os.environ["ENCRYPTION_KEY"] = "test-encryption-not-for-production-0123456789"
os.environ["AUTH_PROVIDER"] = "local"
os.environ.setdefault("DEEPGRAM_API_KEY", "dg-SENTINEL-never-leak-9f3a7c")
import safety
safety.assert_isolated_database(os.environ["DATABASE_URL"])
from fastapi.testclient import TestClient
from app import database, models, publishing_models  # noqa: F401
from app.database import Base, SessionLocal
from app.deps import get_data_user, get_manager_user
from app.main import app

atexit.register(database.engine.dispose)


class OverviewTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(database.engine)
        Base.metadata.create_all(database.engine)
        with SessionLocal() as db:
            owner = models.User(email="a@example.com", full_name="A", hashed_password="x")
            db.add(owner)
            db.flush()
            self.a = models.LinkedInAccount(user_id=owner.id, name="Ada", status="active", daily_action_limit=50)
            self.b = models.LinkedInAccount(user_id=owner.id, name="Bea", status="active", daily_action_limit=50,
                                            management_config={"policy": {"preset": "balanced"}})
            db.add_all([self.a, self.b])
            db.flush()
            campaign = models.Campaign(user_id=owner.id, name="C", account_id=self.a.id)
            db.add(campaign)
            db.flush()
            for status in ["new", "contacted", "contacted", "connected", "replied", "interested"]:
                db.add(models.Lead(user_id=owner.id, campaign_id=campaign.id, status=status))
            db.commit()
            self.owner_id, self.aid, self.bid = owner.id, self.a.id, self.b.id

        def current():
            with SessionLocal() as db:
                return db.get(models.User, self.owner_id)
        app.dependency_overrides[get_data_user] = current
        app.dependency_overrides[get_manager_user] = current
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def test_rates_come_from_the_leads_of_the_accounts_own_campaigns(self):
        data = self.client.get("/linkedin-accounts/overview").json()
        perf = data["accounts"][self.aid]["performance"]
        self.assertEqual((perf["invited"], perf["accepted"], perf["replied"]), (5, 3, 2))
        self.assertEqual(perf["acceptedPercent"], 60.0)
        self.assertEqual(perf["replyPercent"], 66.7)

    def test_an_account_with_no_campaigns_has_no_rates_not_zero(self):
        perf = self.client.get("/linkedin-accounts/overview").json()["accounts"][self.bid]["performance"]
        self.assertIsNone(perf["acceptedPercent"])
        self.assertIsNone(perf["replyPercent"])

    def test_smart_flag_and_usage_ranges_are_present(self):
        data = self.client.get("/linkedin-accounts/overview").json()
        self.assertTrue(data["accounts"][self.bid]["smart"])
        self.assertFalse(data["accounts"][self.aid]["smart"])
        for key in ("connections", "messages"):
            self.assertEqual(set(data["accounts"][self.aid][key]), {"used", "low", "high", "budget"})
        self.assertEqual(data["seatsUsed"], 2)


if __name__ == "__main__":
    unittest.main()
