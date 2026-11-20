"""One audit log for the workspace: LinkedIn actions and assistant/settings changes together, newest first. An admin can delete it all, only after typing
the confirmation word, and the deletion leaves one line saying who cleared it and how many entries went. Other workspaces never see or lose anything."""
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
from fastapi.testclient import TestClient
from app import models
from app.assistant.models import AssistantAudit
from app.database import Base, SessionLocal, engine as db_engine
from app.main import app, _attempts
from app.migrations import migrate

atexit.register(db_engine.dispose)
ORIGIN = {"Origin": "http://localhost:5173"}
PASSWORD = "Strong-Test-Password!"


def register(email):
    c = TestClient(app, headers=ORIGIN)
    r = c.post("/auth", json={"action": "register", "email": email, "fullName": email.split("@")[0].title(), "password": PASSWORD})
    assert r.status_code == 200, r.text
    return c, r.json()["user"]["id"]


class AuditLogTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(db_engine)
        migrate()
        _attempts.clear()
        self.client, self.uid = register("owner@example.com")
        self.addCleanup(self.client.close)
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            account = models.LinkedInAccount(user_id=self.uid, name="Meet Affix", status="active")
            db.add(account)
            db.flush()
            db.add(models.AgentActivity(account_id=account.id, user_id=self.uid, scope="task", step="send_invite", status="ok", result="sent", created_at=now - timedelta(hours=2)))
            db.add(AssistantAudit(workspace_id=self.uid, user_id=self.uid, tool="create_template", kind="write", status="applied", arguments={"name": "Warm"}, created_at=now - timedelta(hours=1)))
            db.commit()
            self.account_id = account.id

    def items(self, **params):
        r = self.client.get("/audit", params=params)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_it_lists_linkedin_actions_and_assistant_changes_together_newest_first(self):
        out = self.items()
        self.assertEqual(out["total"], 2)
        self.assertEqual([i["source"] for i in out["items"]], ["assistant", "linkedin"])
        self.assertIn("Meet Affix", out["items"][1]["who"])
        self.assertTrue(out["canDelete"])
        self.assertEqual(self.items(source="linkedin")["total"], 1)
        self.assertEqual(self.items(source="assistant")["total"], 1)

    def test_changing_the_assistant_settings_is_logged(self):
        r = self.client.put("/assistant/settings", json={"enabled": False})
        self.assertEqual(r.status_code, 200, r.text)
        newest = self.items()["items"][0]
        self.assertEqual((newest["source"], newest["action"]), ("settings", "assistant_settings_changed"))

    def test_deleting_needs_the_confirmation_word_and_leaves_one_line(self):
        self.assertEqual(self.client.request("DELETE", "/audit", json={}).status_code, 422)
        self.assertEqual(self.client.request("DELETE", "/audit", json={"confirm": "yes"}).status_code, 422)
        self.assertEqual(self.items()["total"], 2)
        r = self.client.request("DELETE", "/audit", json={"confirm": "DELETE"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["removed"], 2)
        out = self.items()
        self.assertEqual(out["total"], 1)
        line = out["items"][0]
        self.assertEqual((line["source"], line["action"]), ("settings", "audit_log_cleared"))
        self.assertIn("2", line["detail"])
        with SessionLocal() as db:
            self.assertEqual(db.query(models.AgentActivity).count(), 0)
            self.assertEqual(db.get(models.LinkedInAccount, self.account_id).status, "active")  # nothing but the log is touched

    def test_only_an_admin_can_delete_and_another_workspace_is_untouched(self):
        other, other_id = register("other@example.com")
        self.addCleanup(other.close)
        with SessionLocal() as db:
            db.add(AssistantAudit(workspace_id=other_id, user_id=other_id, tool="create_template", kind="write", status="applied", arguments={}))
            db.commit()
        self.assertEqual(other.get("/audit").json()["total"], 1)  # theirs only
        member, member_id = register("member@example.com")
        self.addCleanup(member.close)
        with SessionLocal() as db:
            db.add(models.TeamMember(owner_id=self.uid, member_id=member_id, email="member@example.com", role="member", status="active"))
            db.commit()
        self.assertFalse(member.get("/audit").json()["canDelete"])
        self.assertEqual(member.request("DELETE", "/audit", json={"confirm": "DELETE"}).status_code, 403)
        self.assertEqual(self.client.request("DELETE", "/audit", json={"confirm": "DELETE"}).status_code, 200)
        self.assertEqual(other.get("/audit").json()["total"], 1)


if __name__ == "__main__":
    unittest.main()
