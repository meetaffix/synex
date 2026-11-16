"""Everything that knows what LinkedIn's pages look like: URLs, selectors and
page-state detection. No other module may hard-code a LinkedIn URL or selector.

UNVERIFIED: the selectors in ``REAL_SELECTORS`` and the paths in ``LINKEDIN`` are
informed guesses. They have never been run against linkedin.com (this project's
rules forbid contacting it from tests). Expect to correct them on first real use,
here and nowhere else. The detection logic is exercised in tests against a local
mock site that is configured with its own ``Selectors``.

Detection never solves, bypasses or outsources a CAPTCHA or checkpoint: any
checkpoint this module does not recognise is reported as MANUAL_VERIFICATION and
the user completes it on LinkedIn themselves.
"""
import random
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum
import re
from typing import Protocol
from urllib.parse import urlsplit

from playwright.async_api import Error as PlaywrightError, Page, TimeoutError as PlaywrightTimeout


class PageState(str, Enum):
    LOGIN_FORM = "login_form"
    LOGGED_IN = "logged_in"
    WRONG_CREDENTIALS = "wrong_credentials"
    CODE_CHALLENGE = "code_challenge"
    CODE_REJECTED = "code_rejected"
    APP_APPROVAL = "app_approval"
    MANUAL_VERIFICATION = "manual_verification"
    RESTRICTED = "restricted"
    PENDING = "pending"  # no recognisable page yet (loading, mid-navigation)


@dataclass(frozen=True)
class Challenge:
    type: str  # email_code | sms_code | authenticator_code
    hint: str | None


@dataclass(frozen=True)
class Profile:
    name: str
    headline: str | None
    url: str
    avatar_url: str | None


@dataclass(frozen=True)
class Selectors:
    username: str
    password: str
    submit: str
    login_error: str
    code_input: str
    code_submit: str
    code_error: str
    code_hint: str
    approval_marker: str
    captcha_marker: str
    logged_in_marker: str
    restricted_marker: str
    profile_name: str
    profile_headline: str
    profile_avatar: str


# Checked on 15 Nov 2026 against LinkedIn's public sign-in page (no login): fields have generated ids, so they are
# found by type; the page has no <form> and the button is type=button with the text "Sign in". Each selector takes the first
# visible match, because the page ships its markup more than once. The code, error and checkpoint selectors are still guesses.
REAL_SELECTORS = Selectors(
    username="input[type=email]:visible >> nth=0",
    password="input[type=password]:visible >> nth=0",
    submit="button:has(span:text-is('Sign in')):visible >> nth=0",
    login_error=":text-matches('not the right password|Wrong email or password|recognize that email|valid username', 'i')",
    code_input="input[name=pin]",
    code_submit="button[type=submit]",
    code_error="#input-error, .form__label--error",
    code_hint="#content p, .app__content p",
    approval_marker="[data-test-id='challenge-app'], :text('LinkedIn app')",
    captcha_marker="iframe[src*='captcha' i], #captcha-internal",
    logged_in_marker="#global-nav, nav.global-nav",
    restricted_marker=":text('account has been restricted')",
    profile_name="main h2",  # fallback only: the name is read from the page title
    profile_headline=".text-body-medium.break-words",
    profile_avatar="img.pv-top-card-profile-picture__image--show",
)

NAVIGATION_TIMEOUT_MS = 30_000
PROXY_ERROR_MARKERS = ("ERR_PROXY", "ERR_TUNNEL_CONNECTION_FAILED", "ERR_SOCKS_CONNECTION")


class LoginSite(Protocol):
    base_url: str

    async def open_login(self, page: Page) -> None: ...
    async def open_feed(self, page: Page) -> None: ...
    async def submit_credentials(self, page: Page, identifier: str, password: str) -> None: ...
    async def submit_code(self, page: Page, code: str) -> None: ...
    async def detect_state(self, page: Page) -> PageState: ...
    async def read_challenge(self, page: Page) -> Challenge: ...
    async def read_profile(self, page: Page) -> Profile: ...
    def is_proxy_error(self, exc: BaseException) -> bool: ...


_TITLE_NAME = re.compile(r"^(?:\(\d+\)\s*)?(?P<name>.+?)\s*\|\s*LinkedIn\s*$")


def name_from_title(title: str) -> str | None:
    """The person's name from a profile page title, or None when the title is not a profile title."""
    match = _TITLE_NAME.match(title.strip())
    name = match.group("name").strip() if match else ""
    return name or None


class Site:
    """Selector-driven implementation of ``LoginSite``."""

    def __init__(self, base_url: str, selectors: Selectors,
                 login_path: str = "/login", feed_path: str = "/feed/", profile_path: str = "/in/me/") -> None:
        self.base_url = base_url.rstrip("/")
        self.sel = selectors
        self._login_path, self._feed_path, self._profile_path = login_path, feed_path, profile_path

    async def open_login(self, page: Page) -> None:
        await page.goto(self.base_url + self._login_path, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)

    async def open_feed(self, page: Page) -> None:
        await page.goto(self.base_url + self._feed_path, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)

    async def submit_credentials(self, page: Page, identifier: str, password: str) -> None:
        await page.fill(self.sel.username, identifier)
        await page.fill(self.sel.password, password)
        await self._click_and_settle(page, self.sel.submit)

    async def submit_code(self, page: Page, code: str) -> None:
        await page.fill(self.sel.code_input, code)
        await self._click_and_settle(page, self.sel.code_submit)

    async def detect_state(self, page: Page) -> PageState:
        sel = self.sel
        path = urlsplit(page.url).path
        if await _visible(page, sel.captcha_marker):
            return PageState.MANUAL_VERIFICATION
        if "/checkpoint" in path:
            if await _visible(page, sel.code_input):
                return PageState.CODE_REJECTED if await _visible(page, sel.code_error) else PageState.CODE_CHALLENGE
            if await _visible(page, sel.approval_marker):
                return PageState.APP_APPROVAL
            return PageState.MANUAL_VERIFICATION
        if path.startswith("/feed") or await _visible(page, sel.logged_in_marker):
            return PageState.LOGGED_IN
        if "/restricted" in path or await _visible(page, sel.restricted_marker):
            return PageState.RESTRICTED
        if await _visible(page, sel.login_error):
            return PageState.WRONG_CREDENTIALS
        if await _visible(page, sel.username):
            return PageState.LOGIN_FORM
        return PageState.PENDING

    async def read_challenge(self, page: Page) -> Challenge:
        hint = await _optional_text(page, self.sel.code_hint)
        return Challenge(type=_challenge_type(hint), hint=hint)

    async def read_profile(self, page: Page) -> Profile:
        await page.goto(self.base_url + self._profile_path, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
        if not urlsplit(page.url).path.startswith("/in/"):  # signed out, or sent to a checkpoint: not a profile
            raise PlaywrightTimeout("the profile page did not open")
        # The real profile page has no <h1> (checked 16 Nov 2026); its title is "<Name> | LinkedIn", sometimes "(3) <Name> | LinkedIn".
        name = name_from_title(await page.title()) or (await page.locator(self.sel.profile_name).first.inner_text(timeout=10_000)).strip()
        avatar = await _optional_attribute(page, self.sel.profile_avatar, "src")
        parts = urlsplit(page.url)
        return Profile(name=name, headline=await _optional_text(page, self.sel.profile_headline),
                       url=f"{parts.scheme}://{parts.netloc}{parts.path}", avatar_url=avatar)

    def is_proxy_error(self, exc: BaseException) -> bool:
        return isinstance(exc, PlaywrightError) and any(marker in str(exc) for marker in PROXY_ERROR_MARKERS)

    @staticmethod
    async def _click_and_settle(page: Page, selector: str) -> None:
        """Click and wait for the resulting navigation, tolerating in-page updates."""
        try:
            async with page.expect_navigation(timeout=15_000):
                await page.click(selector)
        except PlaywrightTimeout:
            pass


LINKEDIN = Site("https://www.linkedin.com", REAL_SELECTORS)


async def _visible(page: Page, selector: str) -> bool:
    try:
        return await page.locator(selector).first.is_visible()
    except PlaywrightError:
        return False


async def _optional_text(page: Page, selector: str) -> str | None:
    try:
        text = await page.locator(selector).first.text_content(timeout=3_000)
    except (PlaywrightError, PlaywrightTimeout):
        return None
    return (text or "").strip() or None


async def _optional_attribute(page: Page, selector: str, name: str) -> str | None:
    try:
        return await page.locator(selector).first.get_attribute(name, timeout=3_000)
    except (PlaywrightError, PlaywrightTimeout):
        return None


def _challenge_type(hint: str | None) -> str:
    text = (hint or "").lower()
    if "authenticator" in text:
        return "authenticator_code"
    if any(word in text for word in ("text message", "sms", "phone")):
        return "sms_code"
    return "email_code"


# --------------------------------------------------------------------------------------
# Outreach actions: profile, invitation and messaging pages.
# UNVERIFIED against the live site, like everything above. Fix selectors here only.
# --------------------------------------------------------------------------------------


class SessionProblem(str, Enum):
    LOGGED_OUT = "logged_out"
    CHECKPOINT = "checkpoint"
    RESTRICTED = "restricted"


@dataclass(frozen=True)
class ProfileSelectors:
    unavailable_marker: str
    connect_button: str
    pending_marker: str
    message_button: str
    follow_button: str
    following_marker: str
    note_toggle: str
    note_input: str
    send_invite_button: str
    invite_limit_marker: str
    note_error: str
    composer_input: str
    composer_send: str
    conversation_item: str  # carries data-thread-id and data-updated-at
    conversation_profile_link: str
    thread_message: str  # carries data-event-id, data-direction (in|out), data-sent-at


# UNVERIFIED against the live site.
REAL_PROFILE_SELECTORS = ProfileSelectors(
    unavailable_marker=":text('Page not found'), :text('Profile is not available')",
    connect_button="button[aria-label^='Invite'][aria-label$='to connect'], button:has-text('Connect')",
    pending_marker="button:has-text('Pending'), button[aria-label^='Pending']",
    message_button="a[aria-label^='Message'], button:has-text('Message')",
    follow_button="button[aria-label^='Follow'], button:has-text('Follow')",
    following_marker="button[aria-label^='Following'], button:has-text('Following')",
    note_toggle="button[aria-label='Add a note']",
    note_input="textarea[name='message']",
    send_invite_button="button[aria-label='Send invitation'], button[aria-label='Send now']",
    invite_limit_marker=":text('weekly invitation limit')",
    note_error="[data-test-note-error]",
    composer_input="div.msg-form__contenteditable, textarea[name='message']",
    composer_send="button.msg-form__send-button",
    conversation_item="li.msg-conversation-listitem",
    conversation_profile_link="a[href*='/in/']",
    thread_message="li.msg-s-message-list__event",
)

NOTE_LIMIT = 300


@dataclass(frozen=True)
class ThreadMessage:
    event_id: str
    direction: str  # in | out
    text: str
    sent_at: str  # ISO 8601


@dataclass(frozen=True)
class ConversationRef:
    thread_id: str
    profile_url: str
    updated_at: str  # ISO 8601


class ProfilePages:
    """Selector-driven profile, invitation and messaging pages."""

    def __init__(self, site: Site, selectors: ProfileSelectors) -> None:
        self.site, self.sel = site, selectors
        self.base_url = site.base_url

    async def goto(self, page: Page, url: str) -> None:
        await page.goto(url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)

    async def session_problem(self, page: Page) -> SessionProblem | None:
        path = urlsplit(page.url).path
        if "/checkpoint" in path or await _visible(page, self.site.sel.captcha_marker):
            return SessionProblem.CHECKPOINT
        if "/restricted" in path or await _visible(page, self.site.sel.restricted_marker):
            return SessionProblem.RESTRICTED
        if path.startswith("/login") or "/uas/login" in path or await _visible(page, self.site.sel.username):
            return SessionProblem.LOGGED_OUT
        return None

    async def profile_unavailable(self, page: Page) -> bool:
        return await _visible(page, self.sel.unavailable_marker)

    async def connection_state(self, page: Page) -> str:
        if await _visible(page, self.sel.pending_marker):
            return "pending"
        if await _visible(page, self.sel.connect_button):
            return "not_connected"
        return "connected" if await _visible(page, self.sel.message_button) else "not_connected"

    async def is_following(self, page: Page) -> bool:
        return await _visible(page, self.sel.following_marker)

    async def can_follow(self, page: Page) -> bool:
        return await _visible(page, self.sel.follow_button)

    async def start_invite(self, page: Page) -> None:
        await self._click_and_settle(page, self.sel.connect_button)

    async def invite_limit_reached(self, page: Page) -> bool:
        return await _visible(page, self.sel.invite_limit_marker)

    async def fill_invite_note(self, page: Page, note: str) -> None:
        if await _visible(page, self.sel.note_toggle):
            await page.click(self.sel.note_toggle)
        await page.fill(self.sel.note_input, note)

    async def submit_invite(self, page: Page) -> None:
        await self._click_and_settle(page, self.sel.send_invite_button)

    async def invite_note_rejected(self, page: Page) -> bool:
        return await _visible(page, self.sel.note_error)

    async def start_message(self, page: Page) -> None:
        await self._click_and_settle(page, self.sel.message_button)

    async def submit_message(self, page: Page, text: str) -> None:
        await page.fill(self.sel.composer_input, text)
        await self._click_and_settle(page, self.sel.composer_send)

    async def follow(self, page: Page) -> None:
        await self._click_and_settle(page, self.sel.follow_button)

    async def last_sent_text(self, page: Page) -> str | None:
        out = page.locator(f"{self.sel.thread_message}[data-direction='out']")
        count = await out.count()
        return (await out.nth(count - 1).inner_text()).strip() if count else None

    async def list_conversations(self, page: Page, since=None) -> list[ConversationRef]:
        await self.goto(page, self.base_url + "/messaging/")
        refs: list[ConversationRef] = []
        items = page.locator(self.sel.conversation_item)
        for index in range(await items.count()):
            item = items.nth(index)
            href = await item.locator(self.sel.conversation_profile_link).first.get_attribute("href")
            thread_id, updated = await item.get_attribute("data-thread-id"), await item.get_attribute("data-updated-at")
            if href and thread_id and updated:
                refs.append(ConversationRef(thread_id, self._absolute(href), updated))
        return refs

    async def read_thread(self, page: Page, thread_id: str) -> list[ThreadMessage]:
        await self.goto(page, f"{self.base_url}/messaging/thread/{thread_id}/")
        messages: list[ThreadMessage] = []
        items = page.locator(self.sel.thread_message)
        for index in range(await items.count()):
            item = items.nth(index)
            event_id, direction = await item.get_attribute("data-event-id"), await item.get_attribute("data-direction")
            sent_at = await item.get_attribute("data-sent-at")
            if event_id and direction in ("in", "out") and sent_at:
                messages.append(ThreadMessage(event_id, direction, (await item.inner_text()).strip(), sent_at))
        return messages

    def _absolute(self, href: str) -> str:
        return href if href.startswith("http") else self.base_url + href

    @staticmethod
    async def _click_and_settle(page: Page, selector: str) -> None:
        await Site._click_and_settle(page, selector)


class LiveProfilePages(ProfilePages):
    """The real messaging pages, read from the structure captured on 16 Nov 2026 (headed browser, Meet Affix).

    The conversation list has no thread id or profile link on its rows, so each row is opened (which is what a person does) and the
    thread's own URL and header link give both. Messages are read in the same visit and handed to ``read_thread`` from a cache, so
    a conversation is opened once per sync. After the first sync only rows with an unread badge are opened. At most
    ``MAX_THREADS`` are opened per sync.
    """

    MAX_THREADS = 10
    ROW = "li.msg-conversation-listitem"
    ROW_LINK = "div.msg-conversation-listitem__link"
    UNREAD = ".msg-conversation-card__unread-count"
    HEADER_LINK = "a.msg-thread__link-to-profile"
    EVENT = "li.msg-s-message-list__event"
    BODY = "p.msg-s-event-listitem__body"

    def __init__(self, site: Site, selectors: ProfileSelectors) -> None:
        super().__init__(site, selectors)
        self._cache: dict[str, list[ThreadMessage]] = {}

    async def list_conversations(self, page: Page, since=None) -> list[ConversationRef]:
        await self.goto(page, self.base_url + "/messaging/")
        try:
            await page.wait_for_selector(f"{self.ROW} {self.ROW_LINK}", timeout=30_000)
        except Exception:  # noqa: BLE001 - an empty inbox is a normal result
            return []
        await page.wait_for_timeout(1500)
        rows = page.locator(self.ROW)
        wanted = []
        for index in range(await rows.count()):
            if since is not None and not await rows.nth(index).locator(self.UNREAD).count():
                continue
            wanted.append(index)
        refs: list[ConversationRef] = []
        for index in wanted[: self.MAX_THREADS]:
            await rows.nth(index).locator(self.ROW_LINK).first.click()
            try:
                await page.wait_for_url("**/messaging/thread/**", timeout=15_000)
                await page.wait_for_selector(self.HEADER_LINK, timeout=15_000)
            except Exception:  # noqa: BLE001 - not a one-to-one thread (group, sponsored): skipped
                continue
            await page.wait_for_timeout(1200)
            thread_id = urlsplit(page.url).path.rstrip("/").rsplit("/", 1)[-1]
            href = await page.locator(self.HEADER_LINK).first.get_attribute("href")
            if not href or "/in/" not in href:
                continue
            self._cache[thread_id] = await self._read_open_thread(page, href)
            refs.append(ConversationRef(thread_id, self._absolute(href), datetime.now(timezone.utc).isoformat()))
            await page.wait_for_timeout(random.uniform(2500, 5500))
        return refs

    async def read_thread(self, page: Page, thread_id: str) -> list[ThreadMessage]:
        if thread_id in self._cache:
            return self._cache.pop(thread_id)
        await self.goto(page, f"{self.base_url}/messaging/thread/{thread_id}/")
        href = await page.locator(self.HEADER_LINK).first.get_attribute("href")
        return await self._read_open_thread(page, href or "")

    async def _read_open_thread(self, page: Page, other_href: str) -> list[ThreadMessage]:
        """Messages of the thread on screen. Direction: a message from the person in the header is incoming, all others are ours."""
        other = normalize_profile(other_href)
        messages: list[ThreadMessage] = []
        sender = None
        events = page.locator(self.EVENT)
        for index in range(await events.count()):
            event = events.nth(index)
            holder = event.locator("[data-event-urn]").first
            urn = await holder.get_attribute("data-event-urn") if await holder.count() else None
            link = event.locator("a[href*='/in/']").first
            if await link.count():
                sender = normalize_profile(await link.get_attribute("href") or "")
            bodies = event.locator(self.BODY)
            if not urn or not await bodies.count():
                continue
            parts = [(await bodies.nth(i).inner_text()).strip() for i in range(await bodies.count())]
            text = chr(10).join(parts).strip()
            direction = "in" if sender and sender == other else "out"
            messages.append(ThreadMessage(urn, direction, text, datetime.now(timezone.utc).isoformat()))
        return messages


def normalize_profile(href: str) -> str:
    match = re.search(r"/in/([^/?#]+)", href or "")
    return match.group(1).lower() if match else ""


PROFILE_PAGES = LiveProfilePages(LINKEDIN, REAL_PROFILE_SELECTORS)
