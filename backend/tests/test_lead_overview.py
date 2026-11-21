"""A lead's overview (campaigns, history, do-not-contact) and adding a lead to a campaign."""
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
from app import database, dnc, models, publishing_models  # noqa: F401
from app.database import Base, SessionLocal
from app.deps import get_current_user, get_data_user, get_manager_user
from app.main import app

atexit.register(database.engine.dispose)


class OverviewTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(database.engine)
        Base.metadata.create_all(database.engine)
        with SessionLocal() as db:
            owner = models.User(email="a@example.com", full_name="A", hashed_password="x")
            other = models.User(email="b@example.com", full_name="B", hashed_password="x")
            db.add_all([owner, other])
            db.flush()
            account = models.LinkedInAccount(user_id=owner.id, name="S", status="active", session_status="connected", daily_action_limit=10)
            db.add(account)
            db.flush()
            lead_list = models.LeadList(user_id=owner.id, name="L")
            db.add(lead_list)
            db.flush()
            self.draft = models.Campaign(user_id=owner.id, name="Draft", status="draft", account_id=account.id, lead_list_id=lead_list.id)
            self.empty = models.Campaign(user_id=owner.id, name="No list", status="draft", account_id=account.id)
            self.live = models.Campaign(user_id=owner.id, name="Live", status="active", account_id=account.id, lead_list_id=lead_list.id)
            lead = models.Lead(user_id=owner.id, first_name="Ada", linkedin_url="https://www.linkedin.com/in/ada-l/", company="Acme")
            foreign = models.Lead(user_id=other.id, first_name="Zed", linkedin_url="https://www.linkedin.com/in/zed/")
            db.add_all([self.draft, self.empty, self.live, lead, foreign])
            db.commit()
            self.owner_id, self.lead_id, self.foreign_id = owner.id, lead.id, foreign.id
            self.ids = {"draft": self.draft.id, "empty": self.empty.id, "live": self.live.id}

        def current():
            with SessionLocal() as db:
                return db.get(models.User, self.owner_id)
        for dep in (get_data_user, get_manager_user, get_current_user):
            app.dependency_overrides[dep] = current
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def overview(self):
        return self.client.get(f"/leads/{self.lead_id}/overview").json()

    def add(self, key):
        return self.client.post(f"/leads/{self.lead_id}/add-to-campaign", json={"campaignId": self.ids[key], "confirmSend": True})

    def test_a_lead_in_no_campaign_says_so_and_another_workspaces_lead_is_hidden(self):
        data = self.overview()
        self.assertEqual((data["campaigns"], data["events"], data["doNotContact"]), ([], [], None))
        self.assertEqual(self.client.get(f"/leads/{self.foreign_id}/overview").status_code, 404)

    def test_adding_to_a_draft_campaign_puts_the_lead_on_its_list_without_starting_anything(self):
        self.assertEqual(self.add("draft").json(), {"added": True, "started": False})
        with SessionLocal() as db:
            self.assertEqual(db.query(models.SequenceRun).count(), 0)
        self.assertEqual(self.add("draft").status_code, 200)  # adding twice is harmless

    def test_adding_to_an_active_campaign_starts_the_sequence_and_the_overview_shows_it(self):
        self.assertEqual(self.add("live").json(), {"added": True, "started": True})
        data = self.overview()
        self.assertEqual([(c["name"], c["runStatus"]) for c in data["campaigns"]], [("Live", "running")])
        self.assertEqual(data["events"][0]["type"], "added_to_campaign")

    def test_a_campaign_without_a_list_or_a_listed_person_is_refused_with_the_reason(self):
        r = self.add("empty")
        self.assertEqual(r.status_code, 409)
        self.assertIn("no lead list", r.json()["detail"])
        with SessionLocal() as db:
            dnc.add_entries(db, self.owner_id, "company", [{"value": "Acme"}], "manual")
            db.commit()
        self.assertEqual(self.overview()["doNotContact"], "company")
        r = self.add("live")
        self.assertEqual(r.status_code, 409)
        self.assertIn("do-not-contact", r.json()["detail"])


if __name__ == "__main__":
    unittest.main()
