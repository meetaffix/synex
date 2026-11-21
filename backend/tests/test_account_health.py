"""The safety score: one number per sender account with plain advice, from Synex's own records."""
import atexit
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

TEMP = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = "sqlite:///" + TEMP.name.replace("\\", "/") + "/test.db"
os.environ["SECRET_KEY"] = "test-secret-not-for-production-0123456789"
os.environ["ENCRYPTION_KEY"] = "test-encryption-not-for-production-0123456789"
os.environ["AUTH_PROVIDER"] = "local"
import safety
safety.assert_isolated_database(os.environ["DATABASE_URL"])
from app import account_health, models
from app.database import Base, SessionLocal, engine as db_engine
from app.migrations import migrate

atexit.register(db_engine.dispose)


class SafetyScoreTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(db_engine)
        migrate()
        self.now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            owner = models.User(email="o@example.com", full_name="O", hashed_password="x")
            db.add(owner)
            db.flush()
            account = models.LinkedInAccount(user_id=owner.id, name="Sender", status="active", session_status="connected",
                                             daily_action_limit=20, warmup_started_at=self.now - timedelta(days=90))
            db.add(account)
            db.commit()
            self.owner_id, self.account_id = owner.id, account.id

    def score(self):
        with SessionLocal() as db:
            return account_health.score(db, db.get(models.LinkedInAccount, self.account_id), self.now)

    def test_a_quiet_established_account_is_healthy(self):
        s = self.score()
        self.assertEqual((s["level"], s["label"]), ("good", "Healthy"))
        self.assertGreaterEqual(s["score"], 75)

    def test_a_restricted_account_is_at_risk_and_says_to_stop(self):
        with SessionLocal() as db:
            db.get(models.LinkedInAccount, self.account_id).session_status = "restricted"
            db.commit()
        s = self.score()
        self.assertEqual(s["level"], "risk")
        self.assertTrue(any("restricted" in a for a in s["advice"]))

    def test_few_accepted_requests_lower_the_score_and_say_why(self):
        with SessionLocal() as db:
            for i in range(12):
                lead = models.Lead(user_id=self.owner_id, first_name=f"L{i}", last_name="T", linkedin_url=f"https://www.linkedin.com/in/l{i}",
                                   status="connected" if i == 0 else "contacted")
                db.add(lead)
                db.flush()
                db.add(models.AgentTask(account_id=self.account_id, type="send_invite", status="done", idempotency_key=f"k{i}", payload={"leadId": lead.id}))
            db.commit()
        s = self.score()
        self.assertEqual(s["acceptanceRate"], 8)
        self.assertLess(s["score"], 75)
        self.assertTrue(any("accepted" in a for a in s["advice"]))


if __name__ == "__main__":
    unittest.main()
