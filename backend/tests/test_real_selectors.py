"""The selectors for linkedin.com are checked against markup shaped like LinkedIn's public sign-in page (read on 15 Nov
2026, no login) and served from memory: linkedin.com is never contacted. A page nothing recognises must fail the attempt
after a short limit instead of hanging for the whole attempt timeout."""
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
from playwright.async_api import async_playwright
from app import database
from app.linkedin_session import manager
from app.linkedin_session.manager import LoginFailed, SessionManager
from app.linkedin_session.pages import LINKEDIN, PageState, REAL_SELECTORS, Site

atexit.register(database.engine.dispose)

# Generated ids, no <form>, the button is type=button with the text "Sign in", and the markup is shipped twice
# (one copy hidden), so a selector must pick the visible one.
FIELDS = """
<div><label for="{n}a"><div>Email or phone</div></label><div><input type="email" id="{n}a" autocomplete="username" value=""/></div></div>
<div><label for="{n}b"><div>Password</div></label><div><input type="password" id="{n}b" autocomplete="current-password" value=""/>
  <button type="button" aria-label="Show password"><span>eye</span></button></div></div>
<div><input type="checkbox" aria-label="Keep me signed in" checked=""/><p>Keep me signed in</p></div>
<button type="button"><span><span>Sign in</span></span></button>
<button type="button"><span><span>Sign in with Google</span></span></button>
"""
REAL_LOGIN_PAGE = (
    '<div id="hidden-copy" style="display:none">' + FIELDS.format(n="h") + "</div>"
    '<div id="visible-copy">' + FIELDS.format(n="v") + "</div>"
)


def with_page(content, check):
    async def scenario():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.set_content(content)
                await check(page)
            finally:
                await browser.close()
    asyncio.run(scenario())


class RealSelectorsTest(unittest.TestCase):
    def test_they_find_the_visible_email_password_and_sign_in_button_on_the_real_page_structure(self):
        async def check(page):
            self.assertIs(await LINKEDIN.detect_state(page), PageState.LOGIN_FORM)
            await page.fill(REAL_SELECTORS.username, "someone@example.com")  # strict mode fails on a double match
            await page.fill(REAL_SELECTORS.password, "not-a-real-password")
            await page.evaluate("""() => document.querySelectorAll('button').forEach(b => b.addEventListener('click', () => { window.__clicked = (window.__clicked || []).concat(b.innerText.trim()); }))""")
            await page.click(REAL_SELECTORS.submit)
            self.assertEqual(await page.evaluate("window.__clicked"), ["Sign in"])  # not "Sign in with Google"
            self.assertEqual(await page.input_value("#visible-copy input[type=email]"), "someone@example.com")
            self.assertEqual(await page.input_value("#hidden-copy input[type=email]", timeout=2000), "")
        with_page(REAL_LOGIN_PAGE, check)

    def test_an_error_message_is_wrong_credentials_and_an_ordinary_page_is_pending(self):
        async def wrong(page):
            self.assertIs(await LINKEDIN.detect_state(page), PageState.WRONG_CREDENTIALS)

        async def other(page):
            self.assertIs(await LINKEDIN.detect_state(page), PageState.PENDING)
        with_page("<p>Hmm, that's not the right password. Please try again.</p>" + REAL_LOGIN_PAGE, wrong)
        with_page("<h1>Some other page</h1>", other)


class StuckPageTest(unittest.TestCase):
    def test_a_page_nothing_recognises_fails_the_attempt_after_the_pending_limit(self):
        class StuckSite(Site):
            async def detect_state(self, page):
                return PageState.PENDING

        class FakePage:
            url = "https://www.linkedin.com/some/page?token=secret"

        mgr = SessionManager(StuckSite("https://example.invalid", REAL_SELECTORS), max_browsers=1, attempt_timeout=600, poll_interval=0.01, headless=True)
        attempt = type("A", (), {"id": "attempt-1"})()
        with patch.object(manager, "PENDING_LIMIT_SECONDS", 0.2), self.assertLogs("synex.linkedin_session", "INFO") as logs:
            with self.assertRaises(LoginFailed) as caught:
                asyncio.run(mgr._drive(attempt, FakePage(), "someone@example.com", "not-a-real-password"))
        self.assertEqual(caught.exception.code, "unknown")
        text = "\n".join(logs.output)
        self.assertIn("page state: pending (path /some/page)", text)  # the path is logged, never the query or a value
        self.assertNotIn("token=secret", text)
        self.assertNotIn("not-a-real-password", text)


if __name__ == "__main__":
    unittest.main()
