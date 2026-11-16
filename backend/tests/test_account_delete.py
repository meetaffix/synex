"""Deleting an account removes it from Synex for good; disconnecting only drops the saved session."""
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
from app.deps import get_admin_user, get_current_user, get_data_user, get_manager_user
from app.linkedin_session import service
from app.main import app

atexit.register(database.engine.dispose)


class FakeManager:
    def __init__(self):
        self.cancelled = []

    def cancel_for_account(self, account_id):
        self.cancelled.append(account_id)


class DeleteTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(database.engine)
        Base.metadata.create_all(database.engine)
        with SessionLocal() as db:
            owner = models.User(email="a@example.com", full_name="A", hashed_password="x")
            db.add(owner)
            db.flush()
            account = models.LinkedInAccount(user_id=owner.id, name="Ada Lovelace", status="active", session_status="connected", daily_action_limit=50,
                                             session_state_encrypted="x")
            db.add(account)
            db.flush()
            db.add(models.AgentTask(account_id=account.id, type="send_message", status="pending", idempotency_key="k1", payload={}))
            db.commit()
            self.owner_id, self.account_id = owner.id, account.id
        self.manager = FakeManager()

        def current():
            with SessionLocal() as db:
                return db.get(models.User, self.owner_id)
        for dep in (get_data_user, get_manager_user, get_admin_user, get_current_user):
            app.dependency_overrides[dep] = current
        app.dependency_overrides[service.get_manager] = lambda: self.manager
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def delete(self, confirm):
        return self.client.post(f"/linkedin-accounts/{self.account_id}/delete", json={"confirm": confirm})

    def test_a_wrong_confirmation_changes_nothing(self):
        self.assertEqual(self.delete("ada").status_code, 422)
        self.assertEqual(len(self.client.get("/linkedin-accounts").json()), 1)
        self.assertEqual(self.manager.cancelled, [])

    def test_the_exact_name_removes_the_account_its_session_and_pending_actions(self):
        self.assertEqual(self.delete("Ada Lovelace").status_code, 204)
        self.assertEqual(self.client.get("/linkedin-accounts").json(), [])
        self.assertEqual(self.manager.cancelled, [self.account_id])
        with SessionLocal() as db:
            account = db.get(models.LinkedInAccount, self.account_id)
            self.assertEqual((account.status, account.daily_action_limit), ("deleted", 0))
            self.assertIsNone(account.session_state_encrypted)
            self.assertEqual(db.query(models.AgentTask).filter_by(account_id=self.account_id).one().status, "cancelled")
        self.assertEqual(self.client.get("/linkedin-accounts/overview").json()["seatsUsed"], 0)

    def test_another_workspaces_account_cannot_be_deleted(self):
        with SessionLocal() as db:
            other = models.User(email="b@example.com", full_name="B", hashed_password="x")
            db.add(other)
            db.flush()
            foreign = models.LinkedInAccount(user_id=other.id, name="Theirs", status="active")
            db.add(foreign)
            db.commit()
            fid = foreign.id
        self.assertEqual(self.client.post(f"/linkedin-accounts/{fid}/delete", json={"confirm": "Theirs"}).status_code, 404)


class InviteLinkTest(DeleteTest):
    def test_a_new_sender_link_creates_a_stopped_account_and_a_one_time_link(self):
        out = self.client.post("/linkedin-accounts/invite-link").json()
        self.assertIn("/reconnect/", out["url"])
        accounts = self.client.get("/linkedin-accounts").json()
        waiting = [a for a in accounts if a["name"].startswith("New sender")]
        self.assertEqual(len(waiting), 1)
        self.assertEqual(waiting[0]["dailyActionLimit"], 0)  # nothing can run until the owner signs in and sets a limit
        self.assertNotEqual(waiting[0]["status"], "connected")


if __name__ == "__main__":
    unittest.main()
