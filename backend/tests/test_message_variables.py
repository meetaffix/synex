"""Message variables: lead facts under both names, sender facts filled when the sender is known, spintax, and a warning for any variable with no value."""
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
from app import database, models, planner, providers, publishing_models  # noqa: F401
from app.database import Base, SessionLocal
from app.deps import get_current_user, get_data_user, get_manager_user
from app.main import app

atexit.register(database.engine.dispose)


class PureTest(unittest.TestCase):
    def test_sender_details_come_from_the_account_name_and_headline(self):
        class Account:
            name, headline = "Grace Hopper", "Rear Admiral at US Navy"
        self.assertEqual(providers.sender_values(Account()), {"sender_firstName": "Grace", "sender_lastName": "Hopper", "sender_company": "US Navy", "sender_title": "Rear Admiral"})
        self.assertEqual(providers.render_sender_variables("From {{sender_firstName}} at {{sender_company}}", Account()), "From Grace at US Navy")
        self.assertEqual(providers.render_sender_variables("{{sender_firstName}}", None), "{{sender_firstName}}")  # no sender yet: left for later

    def test_unresolved_variables_are_named(self):
        self.assertEqual(providers.unresolved_variables("Hi {{first_name}} {{ eventName }} {{x_1}}"), ["eventName", "first_name", "x_1"])
        self.assertEqual(providers.unresolved_variables("plain text"), [])


class ApiTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(database.engine)
        Base.metadata.create_all(database.engine)
        with SessionLocal() as db:
            owner = models.User(email="a@example.com", full_name="A", hashed_password="x")
            db.add(owner)
            db.flush()
            account = models.LinkedInAccount(user_id=owner.id, name="Grace Hopper", headline="Rear Admiral at US Navy", status="active", session_status="connected", daily_action_limit=10)
            lead_list = models.LeadList(user_id=owner.id, name="L")
            db.add_all([account, lead_list])
            db.flush()
            lead = models.Lead(user_id=owner.id, first_name="Ada", last_name="Lovelace", company="Engines", location="London", linkedin_url="https://www.linkedin.com/in/ada/",
                               variables={"eventName": "SaaStr"})
            db.add(lead)
            lead_list.leads.append(lead)
            db.flush()
            campaign = models.Campaign(user_id=owner.id, name="C", status="active", account_id=account.id, lead_list_id=lead_list.id)
            db.add(campaign)
            db.flush()
            db.add(models.CampaignStep(campaign_id=campaign.id, type="connection_request", order=0, message="Hi {{linkedin_firstName}}, I am {{sender_firstName}} from {{sender_company}}. See you at {{eventName}}?"))
            db.commit()
            self.owner_id, self.account_id, self.campaign_id, self.lead_id = owner.id, account.id, campaign.id, lead.id

        def current():
            with SessionLocal() as db:
                return db.get(models.User, self.owner_id)
        for dep in (get_data_user, get_manager_user, get_current_user):
            app.dependency_overrides[dep] = current
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def render(self, text, **extra):
        return self.client.post(f"/campaigns/{self.campaign_id}/drafts/render", json={"text": text, "accountId": self.account_id, **extra})

    def test_the_preview_fills_lead_and_sender_variables_and_names_any_that_have_no_value(self):
        r = self.render("{{linkedin_firstName}} {{linkedin_company}} {{linkedin_location}} {{sender_firstName}} {{eventName}} {{missingThing}}").json()
        self.assertEqual(r["text"], "Ada Engines London Grace SaaStr {{missingThing}}")
        self.assertEqual(r["unresolved"], ["missingThing"])
        self.assertEqual(r["leadName"], "Ada Lovelace")

    def test_shuffle_can_pick_another_spintax_choice_and_a_campaign_without_leads_says_so(self):
        seen = {self.render("{one|two|three|four|five|six}", shuffle=n).json()["text"] for n in range(1, 30)}
        self.assertGreater(len(seen), 1)
        with SessionLocal() as db:
            empty = models.Campaign(user_id=self.owner_id, name="E", status="draft")
            db.add(empty)
            db.commit()
            empty_id = empty.id
        r = self.client.post(f"/campaigns/{empty_id}/drafts/render", json={"text": "hi"})
        self.assertEqual(r.status_code, 409)
        self.assertIn("No data available", r.json()["detail"])

    def test_the_dry_run_shows_the_message_with_the_senders_details_filled_in(self):
        with SessionLocal() as db:
            plans = planner.plan_campaign(db, db.get(models.Campaign, self.campaign_id), datetime.now(timezone.utc))
        self.assertEqual(plans[0].message, "Hi Ada, I am Grace from US Navy. See you at SaaStr?")


if __name__ == "__main__":
    unittest.main()
