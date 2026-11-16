"""The extra lead sources (event, my own posts, Sales Navigator, Recruiter, companies): address checks, company lists, and the collectors run against
pages served from memory through Playwright routes. linkedin.com is never contacted. Unverified on real LinkedIn: no account with access."""
import asyncio
import atexit
import os
import tempfile
import unittest
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
from app import database, lead_sources, models, publishing_models  # noqa: F401
from app.database import Base, SessionLocal
from app.deps import get_data_user, get_manager_user
from app.linkedin_session import collect
from app.main import app

atexit.register(database.engine.dispose)

SEATS = """<ul>
<li><a href="https://www.linkedin.com/sales/lead/ACwAAAda1,NAME_SEARCH,x1"><div>Ada Lovelace</div><div>Engineer at Engines</div><div>London</div></a></li>
<li><a href="https://www.linkedin.com/sales/lead/ACwAAGrace,NAME_SEARCH,x2"><div>Grace Hopper</div><div>Rear Admiral</div><div>New York</div></a></li>
</ul>"""
COMPANIES = """<ul>
<li><a href="https://www.linkedin.com/company/acme-inc/"><div>Acme Inc</div><div>Software Development</div><div>London</div></a></li>
<li><a href="https://www.linkedin.com/company/12345/"><div>Globex</div><div>Manufacturing</div><div>Boston</div></a></li>
</ul>"""
PEOPLE = """<ul>
<li><a href="https://www.linkedin.com/in/katherine-j/"><div>Katherine Johnson</div><div>Mathematician</div><div>Hampton</div></a></li>
<li><a href="https://www.linkedin.com/in/margaret-h/"><div>Margaret Hamilton</div><div>Software lead</div><div>Boston</div></a></li>
</ul>"""
EVENT = f"<html><body><a href='#'>2 attendees</a>{PEOPLE}</body></html>"


def serve(body):
    async def handler(route):
        await route.fulfill(status=200, content_type="text/html", body=f"<html><body>{body}</body></html>")
    return handler


def run_collect(coro_factory):
    async def scenario():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await (await browser.new_context()).new_page()
                found = []

                async def progress(people):
                    found.extend(people)

                async def stop():
                    return False
                await coro_factory(page, progress, stop)
                return found
            finally:
                await browser.close()
    with patch("app.linkedin_session.collect.random.uniform", return_value=0.0):
        return asyncio.run(scenario())


class CollectorTest(unittest.TestCase):
    def test_sales_navigator_and_recruiter_cards_become_profile_addresses(self):
        async def go(page, progress, stop):
            await page.route("https://www.linkedin.com/**", serve(SEATS))
            return await collect.collect_paged(page, "https://www.linkedin.com/sales/search/people?query=x", 10, 1, progress, stop,
                                               collect.read_seat_people, 'a[href*="/sales/lead/"]', pause=lambda: asyncio.sleep(0))
        people = run_collect(go)
        self.assertEqual([p["name"] for p in people], ["Ada Lovelace", "Grace Hopper"])
        self.assertEqual(people[0]["profile_url"], "https://www.linkedin.com/in/ACwAAAda1")
        self.assertEqual(people[0]["headline"], "Engineer at Engines")

    def test_company_results_give_name_industry_and_a_company_page(self):
        async def go(page, progress, stop):
            await page.route("https://www.linkedin.com/**", serve(COMPANIES))
            return await collect.collect_paged(page, "https://www.linkedin.com/search/results/companies/?keywords=x", 10, 1, progress, stop,
                                               collect.read_companies, 'a[href*="/company/"]', pause=lambda: asyncio.sleep(0))
        companies = run_collect(go)
        self.assertEqual([c["name"] for c in companies], ["Acme Inc", "Globex"])
        self.assertEqual(companies[0]["company_url"], "https://www.linkedin.com/company/acme-inc/")
        self.assertEqual(companies[1]["headline"], "Manufacturing")

    def test_event_attendees_are_read_from_the_page(self):
        async def go(page, progress, stop):
            async def handler(route):
                await route.fulfill(status=200, content_type="text/html", body=EVENT)
            await page.route("https://www.linkedin.com/**", handler)
            return await collect.collect_event(page, "https://www.linkedin.com/events/123/", 10, progress, stop)
        people = run_collect(go)
        self.assertEqual({p["name"] for p in people}, {"Katherine Johnson", "Margaret Hamilton"})

    def test_my_own_posts_engagers_are_collected_from_my_recent_posts(self):
        posts = "<a href='https://www.linkedin.com/feed/update/urn:li:activity:1/'>post</a>"

        async def go(page, progress, stop):
            async def handler(route):
                url = route.request.url
                body = posts if "recent-activity" in url else PEOPLE
                await route.fulfill(status=200, content_type="text/html", body=f"<html><body>{body}</body></html>")
            await page.route("https://www.linkedin.com/**", handler)
            return await collect.collect_own_post_engagers(page, 10, progress, stop)
        people = run_collect(go)
        self.assertEqual({p["name"] for p in people}, {"Katherine Johnson", "Margaret Hamilton"})


class SourceApiTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(database.engine)
        Base.metadata.create_all(database.engine)
        with SessionLocal() as db:
            owner = models.User(email="a@example.com", full_name="A", hashed_password="x")
            db.add(owner)
            db.flush()
            account = models.LinkedInAccount(user_id=owner.id, name="S", status="active", session_status="connected", daily_action_limit=0)
            db.add(account)
            db.commit()
            self.owner_id, self.account_id = owner.id, account.id

        def current():
            with SessionLocal() as db:
                return db.get(models.User, self.owner_id)
        app.dependency_overrides[get_data_user] = current
        app.dependency_overrides[get_manager_user] = current
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def make(self, source, params, limit=10):
        return self.client.post("/lead-collections", json={"source": source, "accountId": self.account_id, "limit": limit, "params": params})

    def test_each_source_names_what_is_wrong_with_its_address(self):
        cases = {"event": ("https://example.com/x", "linkedin.com/events/"), "sales_navigator": ("https://www.linkedin.com/search/results/people/", "linkedin.com/sales/"),
                 "recruiter": ("https://www.linkedin.com/sales/search/people", "linkedin.com/talent/"),
                 "companies": ("https://www.linkedin.com/search/results/people/", "/search/results/companies"),
                 "sales_nav_accounts": ("https://www.linkedin.com/sales/search/people", "/sales/search/company")}
        for source, (url, needle) in cases.items():
            r = self.make(source, {"url": url})
            self.assertEqual(r.status_code, 422, source)
            self.assertIn(needle, r.json()["detail"], source)

    def test_post_links_must_be_post_links(self):
        self.assertEqual(self.make("post", {"urls": ["https://www.linkedin.com/in/ada-l/"]}).status_code, 422)
        self.assertEqual(self.make("post", {"urls": ["https://www.linkedin.com/feed/update/urn:li:activity:7001/"]}).status_code, 200)
        self.assertEqual(self.make("post", {"urls": ["https://www.linkedin.com/posts/ada-l_hello-activity-7001-abcd"]}).status_code, 200)

    def test_valid_addresses_are_accepted_for_every_new_source_and_my_own_posts_needs_none(self):
        good = {"event": "https://www.linkedin.com/events/world-summit-123/", "sales_navigator": "https://www.linkedin.com/sales/search/people?query=x",
                "recruiter": "https://www.linkedin.com/talent/search?searchContextId=1", "companies": "https://www.linkedin.com/search/results/companies/?keywords=x",
                "sales_nav_accounts": "https://www.linkedin.com/sales/search/company?query=x"}
        for source, url in good.items():
            self.assertEqual(self.make(source, {"url": url}).status_code, 200, source)
        self.assertEqual(self.make("own_posts", {}).status_code, 200)

    def test_group_is_listed_as_coming_soon_with_the_reason_and_cannot_be_started(self):
        listed = {s["id"]: s for s in self.client.get("/lead-collections/sources").json()}
        self.assertFalse(listed["group"]["available"])
        self.assertIn("Coming soon", listed["group"]["note"])
        self.assertEqual(self.make("group", {"url": "https://www.linkedin.com/groups/1/"}).status_code, 409)
        self.assertTrue(all(listed[k]["available"] for k in ("event", "own_posts", "sales_navigator", "recruiter", "companies", "sales_nav_accounts")))

    def test_company_sources_fill_a_company_list_not_the_leads(self):
        with SessionLocal() as db:
            collection = models.LeadCollection(user_id=self.owner_id, account_id=self.account_id, source="companies", params={}, options={}, list_name="Cos",
                                               max_leads=10, status="running")
            db.add(collection)
            db.flush()
            added = lead_sources.stage(db, collection, [{"company_url": "https://www.linkedin.com/company/acme-inc/", "name": "Acme Inc", "headline": "Software"},
                                                        {"company_url": "https://www.linkedin.com/company/acme-inc", "name": "Acme again"},
                                                        {"company_url": "https://www.linkedin.com/in/not-a-company/", "name": "Nope"}])
            self.assertEqual(added, 1)
            self.assertEqual(lead_sources.import_collection(db, collection), 1)
            db.commit()
            self.assertEqual(db.query(models.Lead).count(), 0)
            self.assertEqual(db.query(models.CompanyEntry).one().name, "Acme Inc")


    def test_the_estimate_is_available_before_anything_is_created(self):
        data = self.client.get("/lead-collections/estimate", params={"source": "sales_navigator", "limit": 2500}).json()
        self.assertTrue(data["reads_linkedin"])
        self.assertEqual(data["pages"], lead_sources.MAX_PAGES_PER_RUN)  # one run never loads more than this many pages
        self.assertEqual(data["people"], lead_sources.MAX_PAGES_PER_RUN * 25)
        self.assertGreaterEqual(data["minutes"], 1)
        local = self.client.get("/lead-collections/estimate", params={"source": "urls", "limit": 40}).json()
        self.assertEqual((local["reads_linkedin"], local["pages"], local["minutes"]), (False, 0, 0))
        self.assertEqual(self.client.get("/lead-collections/estimate", params={"source": "nope"}).status_code, 422)
        self.assertIsNone(data["pagesLeftToday"])
        with_account = self.client.get("/lead-collections/estimate", params={"source": "event", "limit": 50, "accountId": self.account_id}).json()
        self.assertGreater(with_account["pagesLeftToday"], 0)  # reading is allowed even at an outreach limit of 0
        self.assertLessEqual(with_account["pagesLeftToday"], 20)  # never above the collect_leads ceiling

    def test_company_lists_can_be_read_added_to_do_not_contact_and_deleted(self):
        with SessionLocal() as db:
            company_list = models.CompanyList(user_id=self.owner_id, name="Cos")
            db.add(company_list)
            db.flush()
            db.add_all([models.CompanyEntry(list_id=company_list.id, key="linkedin.com/company/acme-inc", name="Acme Inc", url="https://www.linkedin.com/company/acme-inc/"),
                        models.CompanyEntry(list_id=company_list.id, key="linkedin.com/company/12345", name="Globex", url="https://www.linkedin.com/company/12345/")])
            db.commit()
            list_id = company_list.id
        self.assertEqual(self.client.get("/company-lists").json()[0]["count"], 2)
        self.assertEqual(self.client.get(f"/company-lists/{list_id}").json()["total"], 2)
        self.assertEqual(self.client.post(f"/company-lists/{list_id}/do-not-contact").json()["added"], 2)
        self.assertEqual(self.client.post(f"/company-lists/{list_id}/do-not-contact").json()["alreadyListed"], 2)
        self.assertEqual(self.client.delete(f"/company-lists/{list_id}").status_code, 204)
        self.assertEqual(self.client.get("/company-lists").json(), [])
        self.assertEqual(self.client.get(f"/company-lists/{list_id}").status_code, 404)


if __name__ == "__main__":
    unittest.main()
