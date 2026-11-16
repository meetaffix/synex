"""What LinkedIn showed when a login failed: classification, title, URL path and a redacted screenshot, kept locally.
Nothing here contacts linkedin.com: pages are served from memory through Playwright routes."""
import asyncio
import atexit
import os
import tempfile
import unittest
from pathlib import Path
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
from app.linkedin_session.capture import LABELS, capture, classify
from app.linkedin_session.manager import Attempt, LoginFailed, SessionManager
from app.linkedin_session.pages import PageState, REAL_SELECTORS, Site

atexit.register(database.engine.dispose)
HOST = "https://www.example.test"
TYPED = "typed-secret-value-123"


def served(pages: dict[str, str]):
    """Run ``check(page)`` in a real browser where every request to HOST answers from ``pages`` (path -> html)."""
    def decorator(check):
        async def scenario():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    context = await browser.new_context()
                    page = await context.new_page()

                    async def handler(route):
                        from urllib.parse import urlsplit
                        path = urlsplit(route.request.url).path
                        await route.fulfill(status=200, content_type="text/html", body=pages.get(path, "<p>" + "x" * 80 + "</p>"))
                    await context.route(HOST + "/**", handler)
                    await check(page)
                finally:
                    await browser.close()
        asyncio.run(scenario())
    return decorator


class ClassifyTest(unittest.TestCase):
    def kinds(self, html, path="/somewhere", state=None):
        out = {}

        @served({path: html})
        async def run(page):
            await page.goto(HOST + path + "?q=secret-query")
            out["result"] = await classify(None, page, state)
        return out["result"]

    def test_each_kind_of_page_gets_its_own_classification_and_the_path_never_has_the_query(self):
        long_text = "<p>" + "Welcome back, here is some ordinary page text. " * 5 + "</p>"
        cases = [
            ("captcha", '<p>' + "x" * 60 + '</p><iframe src="https://www.example.test/captcha-frame"></iframe>', "/uas/login", None),
            # The ordinary sign-in page ships an invisible reCAPTCHA v3 frame: that is not a CAPTCHA the person must solve.
            ("login_form_not_recognised", long_text + '<input type="email"><input type="password">'
             '<iframe src="https://www.google.com/recaptcha/api2/anchor" style="visibility:hidden"></iframe>', "/login/", None),
            ("checkpoint_other", long_text, "/checkpoint/challenge", None),
            ("authwall", long_text, "/authwall", None),
            ("blocked_or_blank", "<title>Access Denied</title>" + long_text, "/login", None),
            ("blocked_or_blank", "", "/login", None),
            ("login_form_not_recognised", long_text + '<input type="email"><input type="password">', "/login", None),
            ("unknown", long_text, "/somewhere", None),
            ("login_form_error", long_text, "/login", "wrong_credentials"),
            ("checkpoint_code", long_text, "/checkpoint/x", "code_challenge"),
            ("checkpoint_approval", long_text, "/checkpoint/x", "app_approval"),
            ("restricted", long_text, "/restricted", "restricted"),
        ]
        for expected, html, path, state in cases:
            classification, title, seen_path = self.kinds(html, path, state)
            self.assertEqual(classification, expected, (expected, path, state))
            self.assertEqual(seen_path, path)
            self.assertNotIn("secret-query", seen_path)
            self.assertIn(classification, LABELS)

    def test_a_browser_that_never_loaded_anything_is_a_navigation_failure(self):
        async def scenario():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    page = await browser.new_page()
                    self.assertEqual((await classify(None, page))[0], "navigation_failed")
                finally:
                    await browser.close()
        asyncio.run(scenario())


class RedactionTest(unittest.TestCase):
    def test_typed_values_are_cleared_and_hidden_before_the_screenshot_and_the_file_is_written(self):
        folder = Path(TEMP.name) / "captures"
        seen = {}

        @served({"/login": '<p>' + "Sign in to see your network. " * 4 + '</p><input type="email" id="e"><input type="password" id="p">'})
        async def run(page):
            await page.goto(HOST + "/login")
            await page.fill("#e", TYPED)
            await page.fill("#p", TYPED)
            real = page.screenshot

            async def checked(**kwargs):
                seen["values"] = await page.evaluate("[...document.querySelectorAll('input')].map(i => [i.value, getComputedStyle(i).visibility])")
                return await real(**kwargs)
            with patch.object(page, "screenshot", checked):
                seen["diagnosis"] = await capture(None, page, folder, "attempt-xyz")
        d = seen["diagnosis"]
        self.assertEqual(seen["values"], [["", "hidden"], ["", "hidden"]])  # nothing typed was on the page when it was shot
        self.assertEqual(d.classification, "login_form_not_recognised")
        self.assertEqual(d.screenshot, "attempt-xyz-login_form_not_recognised.png")
        self.assertTrue((folder / d.screenshot).stat().st_size > 500)
        self.assertNotIn(TYPED, d.as_log())

    def test_no_directory_means_no_screenshot_but_still_a_classification(self):
        out = {}

        @served({"/login": "<p>" + "y" * 80 + "</p>"})
        async def run(page):
            await page.goto(HOST + "/login")
            out["d"] = await capture(None, page, None, "a1")
        self.assertIsNone(out["d"].screenshot)
        self.assertEqual(out["d"].classification, "unknown")


class AttemptMessageTest(unittest.TestCase):
    def test_an_unknown_or_timeout_failure_says_what_linkedin_showed_and_other_failures_keep_their_message(self):
        from app.linkedin_session.capture import Diagnosis
        mgr = SessionManager(Site(HOST, REAL_SELECTORS), max_browsers=1, attempt_timeout=5, poll_interval=0.01, headless=True)
        attempt = Attempt(id="a", workspace_id="w", key="k", target_account_id=None, token_digest=None)
        attempt.diagnosis = Diagnosis("captcha", "Security Verification", "/checkpoint/challenge", None)
        mgr._fail(attempt, "unknown", "Something went wrong while connecting. Try again.")
        self.assertEqual(attempt.error[1], "Something went wrong while connecting. Try again. LinkedIn showed: a CAPTCHA.")
        mgr._fail(attempt, "invalid_credentials", "LinkedIn did not accept that email, phone number or password.")
        self.assertEqual(attempt.error[1], "LinkedIn did not accept that email, phone number or password.")


class StuckLoginTest(unittest.TestCase):
    def test_an_unrecognised_page_ends_the_attempt_with_a_capture_instead_of_hanging(self):
        folder = Path(TEMP.name) / "stuck"

        class OurSite(Site):
            async def open_login(self, page):
                await page.goto(HOST + "/login")

        class Quick(SessionManager):
            pass

        mgr = SessionManager(OurSite(HOST, REAL_SELECTORS), max_browsers=1, attempt_timeout=600, poll_interval=0.01, headless=True, capture_dir=folder)
        attempt = Attempt(id="stuck1", workspace_id="w", key="k", target_account_id=None, token_digest=None)

        async def scenario():
            async with async_playwright() as p:
                # Serve a sign-in-looking page that the selectors do not match (generated ids, text inputs).
                mgr._playwright = p
                original = mgr._browser

                from contextlib import asynccontextmanager

                @asynccontextmanager
                async def routed(*args, **kwargs):
                    async with original(*args, **kwargs) as (identity, context, page):
                        await context.route(HOST + "/**", lambda route: route.fulfill(
                            status=200, content_type="text/html",
                            body="<p>" + "Please sign in to continue. " * 4 + "</p><input type='text' id='x1'>"))
                        yield identity, context, page
                mgr._browser = routed
                try:
                    with patch.object(manager, "PENDING_LIMIT_SECONDS", 0.3):
                        with self.assertRaises(LoginFailed):
                            await mgr._login(attempt, "someone@example.com", TYPED, None, "Asia/Calcutta", None)
                finally:
                    mgr._playwright = None
        asyncio.run(scenario())
        self.assertEqual(attempt.diagnosis.classification, "login_form_not_recognised")
        self.assertEqual(attempt.diagnosis.path, "/login")
        self.assertTrue((folder / attempt.diagnosis.screenshot).exists())
        self.assertNotIn(TYPED, attempt.diagnosis.as_log())


if __name__ == "__main__":
    unittest.main()
