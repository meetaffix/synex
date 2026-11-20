"""The sender's profile (headline, location, photo) is read from the top card of the profile page. LinkedIn's real profile page
(read on 20 Nov 2026) has no <h1>, no meta tags and generated class names, so the card is read from its text, in order: name,
optional pronouns and badges, headline, location, then "Contact info". Served from memory: linkedin.com is never contacted."""
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
from app.linkedin_session import pages

atexit.register(database.engine.dispose)

# The lines of the real page, as read on 20 Nov 2026 (the first 12 of the main text).
REAL_LINES = ["Meet Affix", "He/Him", "Verify in 2 minutes", "Agentic AI | Computer Science | Digital Marketing",
              "Bengaluru, Karnataka, India", "·", "Contact info", "Nehru Institute of Engineering and Technology",
              "3 connections", "Open to", "Add section", "Enhance profile"]


class ParseTopCardTest(unittest.TestCase):
    def test_the_real_page_gives_headline_and_location(self):
        self.assertEqual(pages.parse_top_card(REAL_LINES, "Meet Affix"),
                         ("Agentic AI | Computer Science | Digital Marketing", "Bengaluru, Karnataka, India"))

    def test_pronouns_badges_and_separators_are_skipped(self):
        lines = ["Ada Lovelace", "She/Her", "Premium", "Verify in 2 minutes", "Engineer", "London", "·", "Contact info"]
        self.assertEqual(pages.parse_top_card(lines, "Ada Lovelace"), ("Engineer", "London"))

    def test_a_card_without_pronouns_or_badges(self):
        self.assertEqual(pages.parse_top_card(["Ada", "Engineer", "London", "Contact info"], "Ada"), ("Engineer", "London"))

    def test_nothing_to_read_gives_none_and_never_guesses(self):
        self.assertEqual(pages.parse_top_card(["Ada", "Some other text"], "Ada"), (None, None))  # no "Contact info": not a top card
        self.assertEqual(pages.parse_top_card(["Ada", "Contact info"], "Ada"), (None, None))

    def test_one_line_is_the_headline_not_a_location(self):
        self.assertEqual(pages.parse_top_card(["Ada", "Engineer", "Contact info"], "Ada"), ("Engineer", None))


def real_shaped_page(photo="https://media.licdn.com/dms/image/v2/X/profile-displayphoto-shrink_800_800/a",
                     banner="https://media.licdn.com/dms/image/v2/Y/profile-displaybackgroundimage-shrink_350_1400/b"):
    lines = "".join(f"<div><span>{line}</span></div>" for line in REAL_LINES)
    return (f"<title>Meet Affix | LinkedIn</title><main><img src='{banner}'><img src='{photo}'>{lines}</main>")


class ReadTopCardTest(unittest.TestCase):
    def run_page(self, content):
        async def scenario():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    page = await browser.new_page()
                    await page.set_content(content)
                    return await pages.read_top_card(page, "Meet Affix", wait_ms=2000)
                finally:
                    await browser.close()
        return asyncio.run(scenario())

    def test_it_reads_headline_location_and_the_profile_photo_not_the_banner(self):
        card = self.run_page(real_shaped_page())
        self.assertEqual((card.headline, card.location), ("Agentic AI | Computer Science | Digital Marketing", "Bengaluru, Karnataka, India"))
        self.assertIn("profile-displayphoto", card.avatar_url)
        self.assertNotIn("background", card.avatar_url)

    def test_a_page_that_has_not_rendered_gives_an_empty_card(self):
        card = self.run_page("<title>Meet Affix | LinkedIn</title><main></main>")
        self.assertEqual((card.headline, card.location, card.avatar_url), (None, None, None))


if __name__ == "__main__":
    unittest.main()
