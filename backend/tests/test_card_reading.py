"""People are read from a page by walking each profile link up to its card. On the real connections page (read on 20 Nov 2026)
there are no list items: each person is a row of plain divs, and the rows sit together inside one shared container. A fixed climb
reached that container, so every person got the first person's name and headline. The card is now the largest ancestor that
holds links to one person only. Served from memory: linkedin.com is never contacted."""
import asyncio
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
from playwright.async_api import async_playwright
from app import database
from app.linkedin_session import collect

atexit.register(database.engine.dispose)


def row(slug, name, headline, connected):
    # The photo link and the name link both point at the profile; the row is a plain div.
    return (f'<div><div><a href="https://www.linkedin.com/in/{slug}/"></a><div><a href="https://www.linkedin.com/in/{slug}/">{name}</a>'
            f"<p>{headline}</p><p>Connected on {connected}</p></div><button>Message</button></div></div>")


REAL_SHAPE = ("<section><div><div><p>3 connections</p>"
              + row("ada", "Ada Lovelace", "Mathematician", "June 18, 2025")
              + row("grace-h", "Grace Hopper", "Rear Admiral", "June 10, 2025")
              + row("alan-t", "Alan Turing", "Computer Scientist", "May 18, 2025")
              + "</div></div></section>")

SEARCH_SHAPE = ('<ul><li><a href="https://www.linkedin.com/in/ada/">Ada Lovelace</a><p>Mathematician</p><p>London</p>'
                '<p>Mutual: <a href="https://www.linkedin.com/in/bob/">Bob</a> and others</p></li>'
                '<li><a href="https://www.linkedin.com/in/grace-h/">Grace Hopper</a><p>Rear Admiral</p><p>New York</p></li></ul>')


class ReadPeopleTest(unittest.TestCase):
    def read(self, content):
        async def scenario():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    page = await browser.new_page()
                    await page.set_content(content)
                    return await collect.read_people(page)
                finally:
                    await browser.close()
        return asyncio.run(scenario())

    def test_rows_that_share_a_container_each_get_their_own_name_and_headline(self):
        people = {p["profile_url"].rstrip("/").rsplit("/", 1)[1]: p for p in self.read(REAL_SHAPE)}
        self.assertEqual(set(people), {"ada", "grace-h", "alan-t"})
        self.assertEqual((people["ada"]["name"], people["ada"]["headline"]), ("Ada Lovelace", "Mathematician"))
        self.assertEqual((people["grace-h"]["name"], people["grace-h"]["headline"]), ("Grace Hopper", "Rear Admiral"))
        self.assertEqual((people["alan-t"]["name"], people["alan-t"]["headline"]), ("Alan Turing", "Computer Scientist"))

    def test_a_search_result_with_a_mutual_connection_link_keeps_its_headline_and_place(self):
        people = {p["profile_url"].rstrip("/").rsplit("/", 1)[1]: p for p in self.read(SEARCH_SHAPE)}
        self.assertEqual((people["ada"]["name"], people["ada"]["headline"], people["ada"]["location"]), ("Ada Lovelace", "Mathematician", "London"))
        self.assertEqual((people["grace-h"]["name"], people["grace-h"]["location"]), ("Grace Hopper", "New York"))


class ParseCardTest(unittest.TestCase):
    def test_the_connected_on_line_is_not_a_location(self):
        person = collect.parse_card("https://www.linkedin.com/in/ada/", "\n".join(["Ada Lovelace", "Mathematician", "Connected on June 18, 2025", "Message"]))
        self.assertEqual((person["name"], person["headline"], person["location"]), ("Ada Lovelace", "Mathematician", ""))


if __name__ == "__main__":
    unittest.main()
