"""A message typed in the inbox goes out at once: it is claimed before older campaign work, the worker does not pace it,
and the hard daily ceiling still applies."""
import atexit
import os
import tempfile
import unittest
from datetime import datetime, timezone

TEMP = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = "sqlite:///" + TEMP.name.replace("\\", "/") + "/test.db"
os.environ["SECRET_KEY"] = "test-secret-not-for-production-0123456789"
os.environ["ENCRYPTION_KEY"] = "test-encryption-not-for-production-0123456789"
os.environ["AUTH_PROVIDER"] = "local"
os.environ.setdefault("DEEPGRAM_API_KEY", "dg-SENTINEL-never-leak-9f3a7c")
import safety
safety.assert_isolated_database(os.environ["DATABASE_URL"])
from fastapi.testclient import TestClient
from app import database, engine, models, outreach_results as results, publishing_models  # noqa: F401
from app.database import Base, SessionLocal
from app.deps import get_current_user, get_data_user, get_manager_user
from app.main import app

atexit.register(database.engine.dispose)


class InstantReplyTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(database.engine)
        Base.metadata.create_all(database.engine)
        with SessionLocal() as db:
            owner = models.User(email="a@example.com", full_name="A", hashed_password="x")
            db.add(owner)
            db.flush()
            account = models.LinkedInAccount(user_id=owner.id, name="S", status="active", session_status="connected", daily_action_limit=50)
            db.add(account)
            db.flush()
            lead = models.Lead(user_id=owner.id, first_name="Ada", last_name="L", linkedin_url="https://www.linkedin.com/in/ada/")
            db.add(lead)
            db.flush()
            convo = models.Conversation(user_id=owner.id, lead_id=lead.id, account_id=account.id)
            db.add(convo)
            db.commit()
            self.owner_id, self.account_id, self.lead_id, self.convo_id = owner.id, account.id, lead.id, convo.id

        def current():
            with SessionLocal() as db:
                return db.get(models.User, self.owner_id)
        for dep in (get_data_user, get_manager_user, get_current_user):
            app.dependency_overrides[dep] = current
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def campaign_task(self, key: str):
        with SessionLocal() as db:
            account = db.get(models.LinkedInAccount, self.account_id)
            task = engine.emit_task(db, account, "send_message", {"leadId": self.lead_id, "message": "Campaign"}, key)
            db.commit()
            return task.id

    def reply(self, body="Thanks, talk soon"):
        return self.client.post("/conversations", json={"action": "reply", "conversationId": self.convo_id, "body": body})

    def test_an_inbox_reply_is_marked_manual_and_claimed_before_older_campaign_work(self):
        older = [self.campaign_task("camp-1"), self.campaign_task("camp-2")]
        r = self.reply()
        self.assertEqual(r.status_code, 200, r.text)
        with SessionLocal() as db:
            manual = db.query(models.AgentTask).filter(models.AgentTask.idempotency_key.like("reply:%")).one()
            self.assertEqual(manual.priority, engine.MANUAL_PRIORITY)
            self.assertTrue(manual.payload["manual"])
            self.assertTrue(results.manual_pending(db, self.account_id))
            self.assertEqual(results.manual_pending_ids(db), {manual.id})
            first = results.claim_next_task(db, self.account_id, "w1", datetime.now(timezone.utc))
            self.assertEqual(first, manual.id)  # the typed reply jumps the queue
            second = results.claim_next_task(db, self.account_id, "w1", datetime.now(timezone.utc))
            self.assertEqual(second, older[0])  # campaign work keeps its own order
            self.assertFalse(results.manual_pending(db, self.account_id))

    def test_campaign_tasks_stay_at_normal_priority(self):
        task_id = self.campaign_task("camp-x")
        with SessionLocal() as db:
            self.assertEqual(db.get(models.AgentTask, task_id).priority, 0)
            self.assertFalse(results.manual_pending(db))

    def test_the_daily_limit_still_refuses_an_inbox_reply(self):
        with SessionLocal() as db:
            db.get(models.LinkedInAccount, self.account_id).daily_action_limit = 0
            db.commit()
        r = self.reply()
        self.assertEqual(r.status_code, 409, r.text)
        with SessionLocal() as db:
            self.assertEqual(db.query(models.AgentTask).count(), 0)

    def test_after_a_reply_goes_out_the_inbox_is_read_sooner_but_never_past_the_ceiling(self):
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            account = db.get(models.LinkedInAccount, self.account_id)
            account.last_inbox_sync_at = now - timedelta(minutes=5)  # read 5 minutes ago: normally too soon to read again
            db.commit()
            self.assertEqual(engine.emit_inbox_syncs(db, now), 0)
            # a reply typed in the inbox has just gone out
            reply = engine.emit_task(db, account, "send_message", {"message": "Hi", "manual": True}, "reply:x", priority=engine.MANUAL_PRIORITY)
            reply.status, reply.updated_at = "done", now
            db.commit()
            self.assertEqual(engine.emit_inbox_syncs(db, now), 1)  # the boost reads it now
            db.commit()
            self.assertEqual(engine.emit_inbox_syncs(db, now), 0)  # one read at a time
            # an hour later the boost is over
            later = now + timedelta(hours=1)
            for t in db.query(models.AgentTask).filter_by(type="sync_inbox"):
                t.status = "done"
            account.last_inbox_sync_at = later - timedelta(minutes=5)
            db.commit()
            self.assertEqual(engine.emit_inbox_syncs(db, later), 0)


if __name__ == "__main__":
    unittest.main()
