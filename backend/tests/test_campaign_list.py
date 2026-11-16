"""The campaigns list: the status a person reads, duplicate, archive, and the shareable sequence file."""
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
from app.deps import get_current_user, get_data_user, get_manager_user
from app.main import app

atexit.register(database.engine.dispose)


class ListCase(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(database.engine)
        Base.metadata.create_all(database.engine)
        with SessionLocal() as db:
            owner = models.User(email="a@example.com", full_name="A", hashed_password="x")
            other = models.User(email="b@example.com", full_name="B", hashed_password="x")
            db.add_all([owner, other])
            db.flush()
            account = models.LinkedInAccount(user_id=owner.id, name="S", status="active", session_status="connected", daily_action_limit=10)
            lead = models.Lead(user_id=owner.id, first_name="Ada", linkedin_url="https://www.linkedin.com/in/ada/")
            db.add_all([account, lead])
            db.flush()
            self.owner_id, self.other_id, self.account_id, self.lead_id = owner.id, other.id, account.id, lead.id
            db.commit()

        def current():
            with SessionLocal() as db:
                return db.get(models.User, self.owner_id)
        for dep in (get_data_user, get_manager_user, get_current_user):
            app.dependency_overrides[dep] = current
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def make(self, name, status="draft", runs=(), **extra):
        with SessionLocal() as db:
            c = models.Campaign(user_id=self.owner_id, name=name, status=status, account_id=self.account_id, **extra)
            db.add(c)
            db.flush()
            db.add(models.CampaignStep(campaign_id=c.id, type="connection_request", order=0, message="hi {{first_name}}", ai_config={"mode": "ai", "tone": "witty", "strategy": "auto", "instructions": "", "profile_data": {"role_company": True}}))
            for run_status in runs:
                db.add(models.SequenceRun(user_id=self.owner_id, campaign_id=c.id, lead_id=self.lead_id, status=run_status))
            db.commit()
            return c.id

    def statuses(self):
        return {c["name"]: c["displayStatus"] for c in self.client.get("/campaigns").json()}


class StatusTest(ListCase):
    def test_each_campaign_shows_the_status_a_person_reads(self):
        self.make("draft")
        self.make("paused", "paused")
        self.make("done", "completed")
        self.make("archived", "archived")
        self.make("queued", "active")
        self.make("running", "active", runs=["running"])
        self.make("quiet", "active", runs=["completed"])
        self.make("failing", "active", runs=["running"], consecutive_failures=3)
        self.assertEqual(self.statuses(), {"draft": "draft", "paused": "paused", "done": "finished", "archived": "archived", "queued": "queued", "running": "running",
                                           "quiet": "no_more_pending", "failing": "failed"})


class RowActionsTest(ListCase):
    def test_duplicate_makes_a_draft_with_the_same_sequence_and_settings_and_nothing_else(self):
        cid = self.make("Original", "active", runs=["running"], exclusions={"existing_connections": True}, ai_context={"goals": "Book demos"},
                        week_schedule={d: {"on": True, "start": "08:00", "end": "20:00"} for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")})
        copy = self.client.post("/campaigns", json={"action": "duplicate", "id": cid}).json()
        self.assertEqual((copy["name"], copy["status"]), ("Copy of Original", "draft"))
        self.assertEqual(copy["steps"][0]["aiConfig"]["tone"], "witty")
        self.assertTrue(copy["exclusions"]["existing_connections"])
        self.assertEqual(copy["aiContext"], {"goals": "Book demos"})
        self.assertIsNone(copy["launchSummary"])
        with SessionLocal() as db:
            self.assertEqual(db.query(models.SequenceRun).filter_by(campaign_id=copy["id"]).count(), 0)
            self.assertNotEqual(db.query(models.CampaignStep).filter_by(campaign_id=copy["id"]).one().id, db.query(models.CampaignStep).filter_by(campaign_id=cid).one().id)

    def test_archive_is_refused_for_a_draft_or_a_running_campaign_and_works_for_a_paused_one(self):
        draft, active, paused = self.make("d"), self.make("a", "active"), self.make("p", "paused")
        for cid in (draft, active):
            r = self.client.post("/campaigns", json={"action": "archive", "id": cid})
            self.assertEqual(r.status_code, 409)
            self.assertIn("Pause or finish", r.json()["detail"])
        self.assertEqual(self.client.post("/campaigns", json={"action": "archive", "id": paused}).json()["status"], "archived")

    def test_the_shared_sequence_has_steps_and_context_but_no_leads_senders_or_runs(self):
        cid = self.make("Shared", ai_context={"goals": "x"})
        data = self.client.get(f"/campaigns/{cid}/share").json()
        self.assertEqual(set(data), {"synexSequence", "name", "sequenceMode", "aiContext", "steps"})
        self.assertEqual(data["steps"][0]["message"], "hi {{first_name}}")
        self.assertNotIn(self.account_id, str(data))

    def test_another_workspaces_campaign_cannot_be_duplicated_archived_or_shared(self):
        with SessionLocal() as db:
            theirs = models.Campaign(user_id=self.other_id, name="Theirs", status="paused")
            db.add(theirs)
            db.commit()
            tid = theirs.id
        self.assertEqual(self.client.post("/campaigns", json={"action": "duplicate", "id": tid}).status_code, 404)
        self.assertEqual(self.client.post("/campaigns", json={"action": "archive", "id": tid}).status_code, 404)
        self.assertEqual(self.client.get(f"/campaigns/{tid}/share").status_code, 404)


if __name__ == "__main__":
    unittest.main()
