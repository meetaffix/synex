"""Saved replies (shortcuts on templates) and sharing a sequence as a file that another workspace can import as a draft."""
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


class Case(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(database.engine)
        Base.metadata.create_all(database.engine)
        with SessionLocal() as db:
            owner = models.User(email="a@example.com", full_name="A", hashed_password="x")
            db.add(owner)
            db.commit()
            self.owner_id = owner.id

        def current():
            with SessionLocal() as db:
                return db.get(models.User, self.owner_id)
        for dep in (get_data_user, get_manager_user, get_current_user):
            app.dependency_overrides[dep] = current
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def template(self, **fields):
        return self.client.post("/templates", json={"action": "create", "name": "Thanks", "category": "reply", "body": "Thanks {{first_name}}!", **fields})


class ShortcutTest(Case):
    def test_a_saved_reply_has_a_shortcut_that_is_cleaned_and_returned(self):
        r = self.template(shortcut="/Thanks").json()
        self.assertEqual(r["shortcut"], "thanks")
        self.assertIsNone(self.template(name="No shortcut").json()["shortcut"])

    def test_a_shortcut_must_be_valid_and_unique_in_the_workspace(self):
        self.assertEqual(self.template(shortcut="x").status_code, 422)
        self.assertEqual(self.template(shortcut="has space").status_code, 422)
        self.assertEqual(self.template(shortcut="thanks").status_code, 200)
        clash = self.template(name="Other", shortcut="thanks")
        self.assertEqual(clash.status_code, 409)
        self.assertIn("already used", clash.json()["detail"])

    def test_a_template_can_keep_its_own_shortcut_when_edited_and_the_shortcut_can_be_cleared(self):
        t = self.template(shortcut="thanks").json()
        same = self.client.post("/templates", json={"action": "update", "id": t["id"], "body": "New text", "shortcut": "thanks"})
        self.assertEqual((same.status_code, same.json()["shortcut"]), (200, "thanks"))
        cleared = self.client.post("/templates", json={"action": "update", "id": t["id"], "shortcut": ""})
        self.assertIsNone(cleared.json()["shortcut"])


class SequenceFileTest(Case):
    def make_campaign(self):
        r = self.client.post("/campaigns", json={"action": "create", "name": "Source", "aiContext": {"goals": "Book demos"}, "steps": [
            {"type": "connection_request", "order": 0, "message": "hi"}, {"type": "wait", "order": 1, "delayHours": 48},
            {"type": "message", "order": 2, "message": "", "aiConfig": {"mode": "ai", "tone": "witty"}}, {"type": "end", "order": 3}]})
        return r.json()["id"]

    def test_a_shared_sequence_imports_as_a_new_draft_with_steps_ai_settings_and_context(self):
        shared = self.client.get(f"/campaigns/{self.make_campaign()}/share").json()
        made = self.client.post("/campaigns", json={"action": "import", "sequence": shared}).json()
        self.assertEqual((made["name"], made["status"]), ("Source", "draft"))
        self.assertEqual([s["type"] for s in made["steps"]], ["connection_request", "wait", "message", "end"])
        self.assertEqual(made["steps"][2]["aiConfig"]["tone"], "witty")
        self.assertEqual(made["aiContext"], {"goals": "Book demos"})
        self.assertIsNone(made["accountId"])
        self.assertEqual(made["leadListId"], None)

    def test_a_file_that_is_not_a_sequence_or_has_an_unknown_step_is_refused_with_the_reason(self):
        for bad, word in (({"hello": 1}, "not a Synex sequence file"), ({"synexSequence": 1, "steps": []}, "not a Synex sequence file"),
                          ({"synexSequence": 1, "steps": [{"type": "teleport"}]}, "Step 1 is not a step Synex knows"),
                          ({"synexSequence": 1, "steps": [{"type": "message", "aiConfig": {"tone": "loud"}}]}, "Tone must")):
            r = self.client.post("/campaigns", json={"action": "import", "sequence": bad})
            self.assertEqual(r.status_code, 422, bad)
            self.assertIn(word, r.text, bad)


if __name__ == "__main__":
    unittest.main()
