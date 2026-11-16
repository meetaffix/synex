"""Lead import: pasted links, CSV with column mapping, existing lists, degree filter and skip options, and queueing a LinkedIn read."""
import atexit
import os
import tempfile
import unittest

TEMP = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = "sqlite:///" + TEMP.name.replace("\\", "/") + "/test.db"
os.environ["SECRET_KEY"] = "test-secret-not-for-production-0123456789"
os.environ["ENCRYPTION_KEY"] = "test-encryption-not-for-production-0123456789"
os.environ["AUTH_PROVIDER"] = "local"
import safety
safety.assert_isolated_database(os.environ["DATABASE_URL"])
from fastapi.testclient import TestClient
from app import database, lead_sources as ls, models
from app.database import Base, SessionLocal
from app.linkedin_session.collect import parse_card
from app.main import app
from app.migrations import migrate

atexit.register(database.engine.dispose)
ORIGIN = {"Origin": "http://localhost:5173"}


class ParsingTest(unittest.TestCase):
    def test_a_search_card_gives_name_degree_headline_and_location(self):
        person = parse_card("https://www.linkedin.com/in/ada", "Ada Lovelace\n• 2nd\nEngineer at Analytical Engines\nLondon, UK\nConnect\n3 mutual connections")
        self.assertEqual((person["name"], person["degree"], person["headline"], person["location"]), ("Ada Lovelace", 2, "Engineer at Analytical Engines", "London, UK"))

    def test_degree_on_the_name_line_and_third_degree_plus(self):
        self.assertEqual(parse_card("u", "Bob Ray • 3rd+\nCEO\nParis")["degree"], 3)
        self.assertEqual(parse_card("u", "Bob Ray\n1st\nCEO")["degree"], 1)
        self.assertIsNone(parse_card("u", "Bob Ray\nCEO")["degree"])

    def test_a_hidden_member_is_skipped(self):
        self.assertIsNone(parse_card("u", "LinkedIn Member\nSomething"))

    def test_pasted_links_are_found_and_the_rest_rejected(self):
        valid, rejected = ls.parse_profile_urls("https://www.linkedin.com/in/ada/\nnot a link\nhttps://in.linkedin.com/in/bob?x=1")
        self.assertEqual(len(valid), 2)
        self.assertEqual(rejected, ["not a link"])

    def test_sheet_link_becomes_a_csv_export_and_other_hosts_are_refused(self):
        self.assertEqual(ls.sheet_export_url("https://docs.google.com/spreadsheets/d/abc_123/edit#gid=7"), "https://docs.google.com/spreadsheets/d/abc_123/export?format=csv&gid=7")
        self.assertIsNone(ls.sheet_export_url("https://evil.example/spreadsheets/d/abc/edit"))

    def test_any_column_names_can_be_mapped_and_the_url_column_is_required(self):
        headers, rows = ls.read_csv("Who,Profile Link,Org\nAda,https://www.linkedin.com/in/ada,Engines\nNoUrl,,X\n")
        guess = ls.suggest_mapping(headers)
        self.assertEqual(guess["linkedin_url"], "Profile Link")
        people, missing = ls.rows_to_people(rows, {**guess, "name": "Who", "company": "Org"})
        self.assertEqual((len(people), missing, people[0]["company"]), (1, 1, "Engines"))
        with self.assertRaises(ValueError):
            ls.rows_to_people(rows, {"name": "Who"})

    def test_the_estimate_caps_pages_and_local_sources_cost_nothing(self):
        self.assertEqual(ls.estimate("urls", 100)["pages"], 0)
        self.assertLessEqual(ls.estimate("search", 100000)["pages"], ls.MAX_PAGES_PER_RUN)


class CollectionApiTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(database.engine)
        migrate()
        self.client = TestClient(app, headers=ORIGIN)
        self.addCleanup(self.client.close)
        r = self.client.post("/auth", json={"action": "register", "email": "owner@example.com", "fullName": "Owner", "password": "Strong-Test-Password!"})
        self.assertEqual(r.status_code, 200, r.text)
        self.user_id = r.json()["user"]["id"]

    def make(self, **body):
        return self.client.post("/lead-collections", json=body)

    def test_pasted_links_preview_import_and_skip_options(self):
        with SessionLocal() as db:
            db.add(models.Lead(user_id=self.user_id, first_name="Old", last_name="Contact", linkedin_url="https://www.linkedin.com/in/old", status="contacted"))
            db.commit()
        text = "https://www.linkedin.com/in/ada\nhttps://www.linkedin.com/in/ada/\nhttps://www.linkedin.com/in/old\nhttps://www.linkedin.com/in/bob"
        made = self.make(source="urls", limit=50, params={"text": text}, options={"skip_contacted": True})
        self.assertEqual(made.status_code, 200, made.text)
        body = made.json()
        self.assertEqual((body["status"], body["fetched"]), ("preview_ready", 3))  # the duplicate is dropped
        done = self.client.post(f"/lead-collections/{body['id']}/run", json={"listName": "My list"}).json()
        self.assertEqual((done["status"], done["created"], done["skipped"]), ("completed", 2, {"already_contacted": 1}))
        with SessionLocal() as db:
            lead_list = db.query(models.LeadList).filter_by(name="My list").one()
            self.assertEqual(len(lead_list.leads), 2)

    def test_degree_filter_and_per_degree_counts_in_the_preview(self):
        with SessionLocal() as db:
            c = models.LeadCollection(user_id=self.user_id, source="search", params={}, options={"degrees": [2]}, list_name="L", max_leads=10, status="previewing")
            db.add(c)
            db.flush()
            ls.stage(db, c, [{"profile_url": f"https://www.linkedin.com/in/p{i}", "name": f"P {i}", "degree": d}
                             for i, d in enumerate([1, 2, 2, 3, None])])
            preview = ls.build_preview(db, c)
            self.assertEqual(preview["degrees"], {"1": 1, "2": 2, "3": 1, "unknown": 1})
            self.assertEqual(ls.import_collection(db, c), 3)  # the two 2nd-degree people and the one whose degree is unknown
            self.assertEqual(c.skipped, {"degree_filter": 2})

    def test_csv_asks_for_the_columns_then_imports(self):
        csv_text = "Who,Link\nAda,https://www.linkedin.com/in/ada\n"
        first = self.make(source="csv", limit=10, params={"text": csv_text}).json()
        self.assertEqual(first["needsMapping"]["suggested"]["linkedin_url"], "Link")
        second = self.make(source="csv", limit=10, params={"text": csv_text, "mapping": {"linkedin_url": "Link", "name": "Who"}}).json()
        self.assertEqual(second["fetched"], 1)
        self.assertEqual(second["detail"], "1 rows read: 1 valid, 0 without a LinkedIn profile link, 0 repeated in the file.")
        messy = "Who,Link\nAda,https://www.linkedin.com/in/ada\nAda again,https://www.linkedin.com/in/ada/\nNo link,\nBob,https://www.linkedin.com/in/bob\n"
        third = self.make(source="csv", limit=10, params={"text": messy, "mapping": {"linkedin_url": "Link", "name": "Who"}}).json()
        self.assertEqual((third["fetched"], third["detail"]), (2, "4 rows read: 2 valid, 1 without a LinkedIn profile link, 1 repeated in the file."))

    def test_a_linkedin_source_needs_a_connected_sender_and_a_valid_link(self):
        self.assertEqual(self.make(source="search", limit=10, params={"url": "https://www.linkedin.com/search/results/people/?keywords=x"}).status_code, 422)
        with SessionLocal() as db:
            account = models.LinkedInAccount(user_id=self.user_id, name="S", status="active", session_status="connected", daily_action_limit=0)
            db.add(account)
            db.commit()
            account_id = account.id
        self.assertEqual(self.make(source="search", limit=10, accountId=account_id, params={"url": "https://example.com"}).status_code, 422)
        made = self.make(source="search", limit=10, accountId=account_id, params={"url": "https://www.linkedin.com/search/results/people/?keywords=x"})
        self.assertEqual(made.status_code, 200, made.text)
        self.assertEqual(made.json()["status"], "draft")
        queued = self.client.post(f"/lead-collections/{made.json()['id']}/preview")  # reading is allowed even at an outreach limit of 0
        self.assertEqual((queued.status_code, queued.json()["status"]), (200, "previewing"))
        again = self.client.post(f"/lead-collections/{made.json()['id']}/preview")
        self.assertEqual(again.status_code, 409)
        with SessionLocal() as db:
            self.assertEqual(db.query(models.AgentTask).filter_by(type="collect_leads").count(), 1)

    def test_unbuilt_sources_say_why_and_limits_are_enforced(self):
        refused = self.make(source="group", limit=10)
        self.assertEqual(refused.status_code, 409)
        self.assertIn("Coming soon", refused.json()["detail"])
        self.assertEqual(self.make(source="urls", limit=5000, params={"text": ""}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
