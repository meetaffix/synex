"""What LinkedIn showed when a login did not finish: a classification, the page title and URL path, and a redacted screenshot.

Local only. The screenshot is written under ``LINKEDIN_CAPTURE_DIR`` (default ``backend/captures``, git-ignored) and is never
sent anywhere. Nothing typed is ever captured: every input is hidden before the screenshot, the query string is dropped from
the URL, and only the page title (not its text) is recorded.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import Error as PlaywrightError, Page

# classification -> the words shown to the user in the connect dialog
LABELS = {
    "login_form_error": "LinkedIn rejected the email or password",
    "login_form_not_recognised": "LinkedIn's sign-in form, which Synex did not recognise",
    "captcha": "a CAPTCHA",
    "checkpoint_code": "a verification code request",
    "checkpoint_approval": "a request to approve the sign-in in the LinkedIn app",
    "checkpoint_other": "a security checkpoint",
    "restricted": "a restricted-account notice",
    "authwall": "a page asking to sign in again",
    "blocked_or_blank": "a blank or blocked page",
    "navigation_failed": "no page at all (the connection to LinkedIn failed or timed out)",
    "proxy_error": "no page at all (the proxy could not be reached)",
    "unknown": "a page Synex did not recognise",
}
BLOCK_WORDS = re.compile(r"access denied|forbidden|blocked|too many requests|unusual traffic|request denied|error 429", re.I)
HIDE_INPUTS = "document.querySelectorAll('input,textarea').forEach(e => { e.value = ''; e.style.visibility = 'hidden'; })"


@dataclass(frozen=True)
class Diagnosis:
    classification: str
    title: str
    path: str
    screenshot: str | None  # file name only

    @property
    def label(self) -> str:
        return LABELS.get(self.classification, LABELS["unknown"])

    def as_log(self) -> str:
        return f"classification={self.classification} path={self.path or '-'} title={self.title or '-'!r} screenshot={self.screenshot or '-'}"


async def _count(page: Page, selector: str) -> int:
    try:
        return await page.locator(selector).count()
    except PlaywrightError:
        return 0


async def classify(site, page: Page, state_name: str | None = None) -> tuple[str, str, str]:
    """(classification, title, path). ``state_name`` is the PageState value the login loop last saw, when it knows."""
    path = urlsplit(page.url).path if page.url else ""
    try:
        title = (await page.title()).strip()[:120]
    except PlaywrightError:
        title = ""
    if not page.url or page.url.startswith("about:"):
        return "navigation_failed", title, path
    mapping = {"wrong_credentials": "login_form_error", "code_challenge": "checkpoint_code", "code_rejected": "checkpoint_code",
               "app_approval": "checkpoint_approval", "restricted": "restricted", "manual_verification": None}
    if state_name in mapping and mapping[state_name]:
        return mapping[state_name], title, path
    if await _count(page, "iframe[src*='captcha' i], #captcha-internal"):
        return "captcha", title, path
    if "/checkpoint" in path:
        return "checkpoint_other", title, path
    if "/authwall" in path:
        return "authwall", title, path
    if BLOCK_WORDS.search(title):
        return "blocked_or_blank", title, path
    visible_fields = await _count(page, "input[type=email]:visible, input[type=password]:visible, input[type=text]:visible")
    if visible_fields:
        return "login_form_not_recognised", title, path
    body_length = 0
    try:
        body_length = await page.evaluate("document.body ? document.body.innerText.trim().length : 0")
    except PlaywrightError:
        pass
    if body_length < 40:
        return "blocked_or_blank", title, path
    return "unknown", title, path


async def capture(site, page: Page, directory: Path | None, attempt_id: str, state_name: str | None = None,
                  force: str | None = None) -> Diagnosis:
    """Classify the current page and save a redacted screenshot. Never raises: a capture must not hide the real failure."""
    try:
        classification, title, path = await classify(site, page, state_name)
    except Exception:  # noqa: BLE001
        classification, title, path = "unknown", "", ""
    if force:
        classification = force
    shot = None
    try:
        if directory is None:
            return Diagnosis(classification, title, path, None)
        await page.evaluate(HIDE_INPUTS)  # typed values and code boxes are inputs: they never reach the screenshot
        directory.mkdir(parents=True, exist_ok=True)
        shot = f"{attempt_id}-{classification}.png"
        await page.screenshot(path=str(directory / shot), full_page=False, timeout=8000)
    except Exception:  # noqa: BLE001
        shot = None
    return Diagnosis(classification, title, path, shot)
