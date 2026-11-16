"""The do-not-contact list: managed through the API, matched by profile or company, and enforced at import, launch and just before every action."""
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
from app import database, dnc, engine, lead_sources, models, outreach_results, publishing_models  # noqa: F401
from app.database import Base, SessionLocal
from app.deps import get_data_user, get_manager_user
from app.main import app

atexit.register(database.engine.dispose)


class DncCase(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(database.engine)
        Base.metadata.create_all(database.engine)
        with SessionLocal() as db:
            owner = models.User(email="a@example.com", full_name="A", hashed_password="x")
            other = models.User(email="b@example.com", full_name="B", hashed_password="x")
            db.add_all([owner, other])
            db.commit()
            self.owner_id, self.other_id = owner.id, other.id

        def current():
            with SessionLocal() as db:
                return db.get(models.User, self.owner_id)
        app.dependency_overrides[get_data_user] = current
        app.dependency_overrides[get_manager_user] = current
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def add(self, kind, text):
        return self.client.post("/do-not-contact", json={"kind": kind, "text": text})


class ApiTest(DncCase):
    def test_people_are_added_deduplicated_and_bad_lines_counted(self):
        r = self.add("person", "https://www.linkedin.com/in/ada-l/\nhttps://linkedin.com/in/ada-l?trk=x\nnot a link\nhttps://www.linkedin.com/in/grace-h")
        self.assertEqual(r.json(), {"added": 2, "alreadyListed": 1, "invalid": 1})
        self.assertEqual(self.client.get("/do-not-contact", params={"kind": "person"}).json()["total"], 2)
        self.assertEqual(self.client.get("/do-not-contact", params={"kind": "company"}).json()["total"], 0)

    def test_companies_match_ignoring_case_spaces_and_punctuation_and_accept_company_pages(self):
        r = self.add("company", "Acme, Inc.\nacme inc\nhttps://www.linkedin.com/company/globex-corp/")
        self.assertEqual(r.json(), {"added": 2, "alreadyListed": 1, "invalid": 0})
        with SessionLocal() as db:
            self.assertEqual(dnc.blocked_key(db, self.owner_id, "", "ACME INC"), "company")
            self.assertEqual(dnc.blocked_key(db, self.owner_id, "", "Globex Corp"), "company")
            self.assertIsNone(dnc.blocked_key(db, self.owner_id, "", "Initech"))

    def test_search_import_export_and_remove(self):
        self.add("person", "https://www.linkedin.com/in/ada-l/")
        text = "linkedin_url,name\nhttps://www.linkedin.com/in/new-one/,New One\nbad,Nobody\n"
        self.assertEqual(self.client.post("/do-not-contact/import", json={"kind": "person", "csv": text}).json(), {"added": 1, "alreadyListed": 0, "invalid": 1})
        self.assertEqual(self.client.get("/do-not-contact", params={"q": "new-one"}).json()["total"], 1)
        export = self.client.get("/do-not-contact/export", params={"kind": "person"})
        self.assertEqual(export.headers["content-type"].split(";")[0], "text/csv")
        self.assertEqual(len(export.text.strip().splitlines()), 3)
        entry = self.client.get("/do-not-contact", params={"q": "ada"}).json()["items"][0]
        self.assertEqual(self.client.delete(f"/do-not-contact/{entry['id']}").status_code, 204)
        self.assertEqual(self.client.get("/do-not-contact").json()["total"], 1)

    def test_a_file_without_the_right_column_is_refused_with_the_fix(self):
        r = self.client.post("/do-not-contact/import", json={"kind": "person", "csv": "name\nAda\n"})
        self.assertEqual(r.status_code, 422)
        self.assertIn("linkedin_url", r.json()["detail"])
        r = self.client.post("/do-not-contact/import", json={"kind": "company", "csv": "x\n1\n"})
        self.assertIn("company", r.json()["detail"])

    def test_formulas_are_neutralised_in_the_export_and_another_workspace_is_invisible(self):
        self.add("company", "=HYPERLINK(\"http://evil\")")
        self.assertIn("'=HYPERLINK", self.client.get("/do-not-contact/export", params={"kind": "company"}).text)
        with SessionLocal() as db:
            db.add(models.DoNotContact(user_id=self.other_id, kind="person", key="linkedin.com/in/theirs", name="", source="manual"))
            db.commit()
            entry_id = db.query(models.DoNotContact).filter_by(user_id=self.other_id).one().id
        self.assertEqual(self.client.get("/do-not-contact", params={"kind": "person"}).json()["total"], 0)
        self.assertEqual(self.client.delete(f"/do-not-contact/{entry_id}").status_code, 404)


class EnforcementTest(DncCase):
    def setUp(self):
        super().setUp()
        with SessionLocal() as db:
            account = models.LinkedInAccount(user_id=self.owner_id, name="Ada", status="active", session_status="connected", daily_action_limit=50)
            db.add(account)
            db.flush()
            campaign = models.Campaign(user_id=self.owner_id, name="C", status="active", account_id=account.id)
            lead_list = models.LeadList(user_id=self.owner_id, name="L")
            db.add_all([campaign, lead_list])
            db.flush()
            campaign.lead_list_id = lead_list.id
            self.leads = {}
            for name, url, company in (("ok", "https://www.linkedin.com/in/fine/", "Fine Co"), ("person", "https://www.linkedin.com/in/blocked-person/", "Fine Co"),
                                       ("company", "https://www.linkedin.com/in/someone/", "Blocked Co")):
                lead = models.Lead(user_id=self.owner_id, first_name=name, linkedin_url=url, company=company)
                db.add(lead)
                lead_list.leads.append(lead)
                db.flush()
                self.leads[name] = lead.id
            db.add(models.CampaignStep(campaign_id=campaign.id, type="connection_request", order=0, message="hi"))
            db.commit()
            self.campaign_id, self.account_id = campaign.id, account.id
        self.add("person", "https://www.linkedin.com/in/blocked-person/")
        self.add("company", "blocked co")

    def test_launch_never_starts_a_blocked_person_or_company(self):
        with SessionLocal() as db:
            created = engine.launch_campaign(db, db.get(models.Campaign, self.campaign_id))
            db.commit()
            started = {r.lead_id for r in db.query(models.SequenceRun).filter_by(campaign_id=self.campaign_id)}
        self.assertEqual(created, 1)
        self.assertEqual(started, {self.leads["ok"]})

    def test_a_queued_action_is_skipped_when_the_person_is_added_after_it_was_queued(self):
        with SessionLocal() as db:
            run = models.SequenceRun(user_id=self.owner_id, campaign_id=self.campaign_id, lead_id=self.leads["ok"], status="awaiting_agent")
            db.add(run)
            db.flush()
            task = models.AgentTask(account_id=self.account_id, sequence_run_id=run.id, type="send_invite", status="pending", idempotency_key="k1",
                                    payload={"leadId": self.leads["ok"]})
            db.add(task)
            db.commit()
            task_id = task.id
        self.assertIsNone(outreach_results.precheck(task_id))
        self.add("person", "https://www.linkedin.com/in/fine/")
        self.assertEqual(outreach_results.precheck(task_id), "lead_do_not_contact")

    def test_an_import_leaves_out_listed_people_and_companies_and_says_so(self):
        with SessionLocal() as db:
            self.assertEqual(lead_sources.exclusion_reason(db, self.owner_id, "linkedin.com/in/blocked-person", {}), "do_not_contact")
            self.assertEqual(lead_sources.exclusion_reason(db, self.owner_id, "linkedin.com/in/new", {}, "Blocked Co"), "do_not_contact")
            self.assertIsNone(lead_sources.exclusion_reason(db, self.owner_id, "linkedin.com/in/new", {}, "Fine Co"))


if __name__ == "__main__":
    unittest.main()
