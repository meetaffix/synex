"""An account's own connection list and received invitations: stored, searched, exported, imported, and read by a paced task that is counted
against its own ceiling. The LinkedIn pages are served from memory through Playwright routes: linkedin.com is never contacted."""
import asyncio
import atexit
import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

TEMP = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = "sqlite:///" + TEMP.name.replace("\\", "/") + "/test.db"
os.environ["SECRET_KEY"] = "test-secret-not-for-production-0123456789"
os.environ["ENCRYPTION_KEY"] = "test-encryption-not-for-production-0123456789"
os.environ["AUTH_PROVIDER"] = "local"
os.environ.setdefault("DEEPGRAM_API_KEY", "dg-SENTINEL-never-leak-9f3a7c")
import safety
safety.assert_isolated_database(os.environ["DATABASE_URL"])
from fastapi.testclient import TestClient
from playwright.async_api import async_playwright
from app import connections_runner, database, models, publishing_models  # noqa: F401
from app.config import DAILY_TYPE_CEILINGS
from app.database import Base, SessionLocal
from app.deps import get_data_user, get_manager_user
from app.linkedin_session.actions import ActionSession
from app.linkedin_session.pages import PROFILE_PAGES
from app.main import app

atexit.register(database.engine.dispose)

PEOPLE = """<ul>
<li><a href="https://www.linkedin.com/in/ada-l/"><div>Ada Lovelace</div><div>Engineer at Analytical Engines</div><div>London</div></a></li>
<li><a href="https://www.linkedin.com/in/grace-h/"><div>Grace Hopper</div><div>Rear Admiral</div><div>New York</div></a></li>
<li><a href="https://www.linkedin.com/in/margaret-h/"><div>Margaret Hamilton</div><div>Software lead</div><div>Boston</div></a></li>
</ul>"""
INVITERS = """<ul><li><a href="https://www.linkedin.com/in/katherine-j/"><div>Katherine Johnson</div><div>Mathematician</div><div>Hampton</div></a></li></ul>"""


class ConnectionsCase(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(database.engine)
        Base.metadata.create_all(database.engine)
        with SessionLocal() as db:
            owner = models.User(email="a@example.com", full_name="A", hashed_password="x")
            other = models.User(email="b@example.com", full_name="B", hashed_password="x")
            db.add_all([owner, other])
            db.flush()
            account = models.LinkedInAccount(user_id=owner.id, name="Ada", status="active", session_status="connected", daily_action_limit=50,
                                             session_state_encrypted="x", browser_profile={"userAgent": "x"})
            foreign = models.LinkedInAccount(user_id=other.id, name="Theirs", status="active", session_status="connected", daily_action_limit=50)
            db.add_all([account, foreign])
            db.commit()
            self.owner_id, self.account_id, self.foreign_id = owner.id, account.id, foreign.id

        def current():
            with SessionLocal() as db:
                return db.get(models.User, self.owner_id)

        app.dependency_overrides[get_data_user] = current
        app.dependency_overrides[get_manager_user] = current
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def url(self, path="", account=None):
        return f"/linkedin-accounts/{account or self.account_id}/connections{path}"

    def store(self, kind="connection"):
        connections_runner.upsert(self.account_id, kind, [
            {"profile_url": "https://www.linkedin.com/in/ada-l/", "name": "Ada Lovelace", "headline": "Engineer", "location": "London"},
            {"profile_url": "https://www.linkedin.com/in/grace-h/", "name": "Grace Hopper", "headline": "Admiral", "location": "New York"},
            {"profile_url": "https://www.linkedin.com/in/=cmd-x/", "name": "=HYPERLINK(\"http://evil\")", "headline": "", "location": ""}])


class ListSearchTest(ConnectionsCase):
    def test_the_list_is_searchable_paged_and_split_by_kind(self):
        self.store()
        self.store("invitation")
        data = self.client.get(self.url()).json()
        self.assertEqual(data["total"], 3)
        self.assertEqual({row["name"] for row in data["items"]}, {"Ada Lovelace", "Grace Hopper", '=HYPERLINK("http://evil")'})
        self.assertEqual(self.client.get(self.url(), params={"q": "london"}).json()["total"], 1)
        self.assertEqual(self.client.get(self.url(), params={"q": "ADMIRAL"}).json()["items"][0]["name"], "Grace Hopper")
        self.assertEqual(len(self.client.get(self.url(), params={"limit": 2}).json()["items"]), 2)
        self.assertEqual(self.client.get(self.url(), params={"kind": "invitation"}).json()["total"], 3)
        self.assertEqual(self.client.get(self.url(), params={"kind": "bogus"}).status_code, 422)

    def test_another_workspaces_account_is_not_readable_or_writable(self):
        for call in (lambda: self.client.get(self.url(account=self.foreign_id)), lambda: self.client.get(self.url("/export", self.foreign_id)),
                     lambda: self.client.post(self.url("/reload", self.foreign_id), json={}),
                     lambda: self.client.post(self.url("/import", self.foreign_id), json={"csv": "linkedin_url\n"})):
            self.assertEqual(call().status_code, 404)


class ExportImportTest(ConnectionsCase):
    def test_the_export_is_a_csv_and_neutralises_spreadsheet_formulas(self):
        self.store()
        response = self.client.get(self.url("/export"))
        self.assertEqual(response.headers["content-type"].split(";")[0], "text/csv")
        self.assertIn("attachment", response.headers["content-disposition"])
        lines = response.text.strip().splitlines()
        self.assertEqual(lines[0], "linkedin_url,name,headline,location")
        self.assertEqual(len(lines), 4)
        self.assertNotIn(',=HYPERLINK', response.text)  # the formula is stored with a leading apostrophe
        self.assertIn("'=HYPERLINK", response.text)

    def test_the_upload_adds_new_people_skips_known_ones_and_counts_bad_rows(self):
        self.store()
        text = ("linkedin_url,name\nhttps://www.linkedin.com/in/ada-l/,Ada Again\nhttps://www.linkedin.com/in/new-person/,New Person\n"
                "https://www.linkedin.com/in/new-person/,New Person\nnot a url,Nobody\n\n")
        out = self.client.post(self.url("/import"), json={"csv": text}).json()
        self.assertEqual(out, {"added": 1, "alreadyStored": 1, "duplicatesInFile": 1, "invalid": 1})
        self.assertEqual(self.client.get(self.url()).json()["total"], 4)
        self.assertEqual(self.client.get(self.url(), params={"q": "Ada"}).json()["items"][0]["name"], "Ada Again")  # a refresh, never a duplicate

    def test_a_file_without_the_linkedin_url_column_is_refused_with_the_fix(self):
        response = self.client.post(self.url("/import"), json={"csv": "name,email\nAda,a@example.com\n"})
        self.assertEqual(response.status_code, 422)
        self.assertIn("linkedin_url", response.json()["detail"])


class ReloadTest(ConnectionsCase):
    def test_a_reload_queues_one_task_and_a_second_while_it_waits_is_refused(self):
        first = self.client.post(self.url("/reload"), json={"kind": "connection"})
        self.assertEqual(first.status_code, 202)
        self.assertEqual(first.json()["sync"]["status"], "queued")
        with SessionLocal() as db:
            tasks = db.query(models.AgentTask).filter_by(account_id=self.account_id, type="sync_connections").all()
            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0].payload, {"accountId": self.account_id, "kind": "connection"})
        self.assertEqual(self.client.post(self.url("/reload"), json={"kind": "connection"}).status_code, 409)
        self.assertEqual(self.client.post(self.url("/reload"), json={"kind": "invitation"}).status_code, 202)  # a different list is separate

    def test_it_stops_at_its_own_daily_ceiling(self):
        ceiling = DAILY_TYPE_CEILINGS["sync_connections"]
        with SessionLocal() as db:
            for i in range(ceiling):
                db.add(models.AgentTask(account_id=self.account_id, type="sync_connections", status="done", idempotency_key=f"k{i}",
                                        committed_at=datetime.now(timezone.utc), payload={}))
            db.commit()
        response = self.client.post(self.url("/reload"), json={})
        self.assertEqual(response.status_code, 429)
        self.assertIn("today's limit", response.json()["detail"])

    def test_a_disconnected_account_cannot_be_read(self):
        with SessionLocal() as db:
            db.get(models.LinkedInAccount, self.account_id).status = "disconnected"
            db.commit()
        self.assertEqual(self.client.post(self.url("/reload"), json={}).status_code, 409)


class RunnerTest(ConnectionsCase):
    def run_kind(self, kind):
        async def scenario():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    page = await (await browser.new_context()).new_page()

                    async def handler(route):
                        url = route.request.url
                        body = INVITERS if "invitation-manager" in url else PEOPLE
                        await route.fulfill(status=200, content_type="text/html", body=f"<html><body>{body}</body></html>")
                    await page.route("https://www.linkedin.com/**", handler)
                    with patch("app.linkedin_session.collect.random.uniform", return_value=0.0):  # no human pauses in a test
                        return await connections_runner.run(ActionSession(page=page, pages=PROFILE_PAGES), self.account_id, kind)
                finally:
                    await browser.close()
        return asyncio.run(scenario())

    def test_the_runner_stores_the_connection_list_and_marks_the_read_done(self):
        self.assertEqual(self.run_kind("connection"), "synced")
        data = self.client.get(self.url()).json()
        self.assertEqual({row["name"] for row in data["items"]}, {"Ada Lovelace", "Grace Hopper", "Margaret Hamilton"})
        self.assertEqual(data["sync"]["status"], "done")
        self.assertEqual(data["sync"]["lastAdded"], 3)
        self.assertTrue(data["sync"]["lastSyncedAt"])
        self.assertEqual(self.run_kind("connection"), "synced")  # a second read refreshes, never duplicates
        self.assertEqual(self.client.get(self.url()).json()["total"], 3)

    def test_the_runner_reads_received_invitations_into_their_own_list(self):
        self.run_kind("invitation")
        self.assertEqual([row["name"] for row in self.client.get(self.url(), params={"kind": "invitation"}).json()["items"]], ["Katherine Johnson"])
        self.assertEqual(self.client.get(self.url()).json()["total"], 0)


if __name__ == "__main__":
    unittest.main()
