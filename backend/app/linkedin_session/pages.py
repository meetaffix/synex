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
import logging

log = logging.getLogger("synex.linkedin_session")


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
    # Read from the top card; unverified on real LinkedIn (selectors are best guesses until a read test is approved).
    location: str | None = None
    company: str | None = None


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
    profile_location: str = ".text-body-small.inline.t-black--light.break-words"
    profile_company: str = "button[aria-label^='Current company' i] span, .pv-text-details__right-panel li button span"


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
                 login_path: str = "/login", feed_path: str = "/feed/", profile_path: str = "/in/me/",
                 text_profile: bool = False) -> None:
        self.base_url = base_url.rstrip("/")
        self.sel = selectors
        self.text_profile = text_profile  # read the profile's top card from its text: the real page has no stable selectors
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
        card = await read_top_card(page, name) if self.text_profile else TopCard(None, None, None)
        parts = urlsplit(page.url)
        return Profile(name=name, headline=card.headline or await _optional_text(page, self.sel.profile_headline),
                       url=f"{parts.scheme}://{parts.netloc}{parts.path}",
                       avatar_url=card.avatar_url or await _optional_attribute(page, self.sel.profile_avatar, "src"),
                       location=card.location or await _optional_text(page, self.sel.profile_location),
                       company=await _optional_text(page, self.sel.profile_company))

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


LINKEDIN = Site("https://www.linkedin.com", REAL_SELECTORS, text_profile=True)


async def _first_visible(locator):
    """The first match that is actually on screen, or None. Hidden duplicates are skipped."""
    try:
        count = min(await locator.count(), 12)
        for index in range(count):
            item = locator.nth(index)
            if await item.is_visible():
                return item
    except PlaywrightError:
        return None
    return None


async def _visible_anywhere(page: Page, selector: str):
    """The first on-screen match in the page or in LinkedIn's embedded messaging frame, or None."""
    frames = [page.main_frame, *[f for f in page.frames if "/preload" in (f.url or "") or "/messaging" in (f.url or "")]]
    for frame in frames:
        try:
            found = await _first_visible(frame.locator(selector))
        except PlaywrightError:
            found = None
        if found is not None:
            return found
    return None


async def _visible(page: Page, selector: str) -> bool:
    try:
        return await _first_visible(page.locator(selector)) is not None
    except PlaywrightError:
        return False


@dataclass(frozen=True)
class TopCard:
    headline: str | None
    location: str | None
    avatar_url: str | None


# The real profile page (read on 20 Nov 2026) has no <h1>, no meta tags and generated class names. Its top card is text, in this
# order: name, optional pronouns and badges, headline, location, "Contact info". Anchoring on the name and on "Contact info"
# survives class renames; the lines between them, minus pronouns, badges and separators, are the headline and the location.
_PRONOUNS = re.compile(r"^(he|she|they|ze|xe|it)\s*/\s*\w+", re.I)
_BADGE = re.compile(r"^(verify in|premium|verified|open to work|hiring|\d+(st|nd|rd))", re.I)


def parse_top_card(lines: list[str], name: str) -> tuple[str | None, str | None]:
    """(headline, location) from the main text lines of a profile page. (None, None) when this is not a top card."""
    end = next((i for i, line in enumerate(lines) if line.strip().lower() == "contact info"), None)
    if end is None:
        return None, None
    start = next((i for i, line in enumerate(lines[:end]) if line.strip() == name), -1)
    body = [line.strip() for line in lines[start + 1:end]
            if re.search(r"\w", line) and not _PRONOUNS.match(line.strip()) and not _BADGE.match(line.strip())]
    if not body:
        return None, None
    if len(body) == 1:
        return body[0], None
    return body[-2], body[-1]


_TOP_CARD_JS = r"""() => {
  const main = document.querySelector('main');
  if (!main) return null;
  const photo = [...main.querySelectorAll('img')].map(i => i.currentSrc || i.src).find(s => /profile-displayphoto/i.test(s || ''));
  return {lines: main.innerText.split('\n').map(s => s.trim()).filter(Boolean).slice(0, 40), photo: photo || null};
}"""


async def read_top_card(page: Page, name: str, wait_ms: int = 15_000) -> TopCard:
    """Headline, location and profile photo from the top card. Waits for the card to render (the page paints after the
    document loads); an empty card, never an error, when it does not."""
    try:
        await page.wait_for_function("() => { const m = document.querySelector('main'); return !!m && /Contact info/i.test(m.innerText); }",
                                     timeout=wait_ms)
        data = await page.evaluate(_TOP_CARD_JS)
    except (PlaywrightError, PlaywrightTimeout):
        return TopCard(None, None, None)
    if not data:
        return TopCard(None, None, None)
    headline, location = parse_top_card(data["lines"], name)
    return TopCard(headline, location, data["photo"])


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
    like_button: str = ""  # the Like control of a post on the person's activity page
    liked_marker: str = ""  # shown once a post is liked
    no_posts_marker: str = ""
    inmail_button: str = ""  # opens the InMail composer for someone not connected
    inmail_subject: str = ""
    inmail_body: str = ""
    inmail_send: str = ""
    inmail_free_marker: str = ""  # shown when the message is free (an open profile)
    inmail_no_credits_marker: str = ""
    attach_input: str = ""  # the file input of the conversation composer
    attach_send: str = ""
    reaction_open: str = ""  # the Like control that opens the reaction picker on a post page
    reaction_choice: str = ""  # one reaction in the picker; {name} is replaced by its label, for example Celebrate
    reacted_marker: str = ""
    comment_box: str = ""
    comment_submit: str = ""
    # The profile's own header (name, headline, its buttons). Connection buttons are read only inside it. Empty means the whole page.
    top_card: str = ""
    # A message bubble in an open conversation, used to confirm a send where the page has no data-direction marker (real LinkedIn).
    sent_body: str = ""


# UNVERIFIED against the live site.
REAL_PROFILE_SELECTORS = ProfileSelectors(
    # The first section of the main column is the profile header; the right rail (an aside) holds other people's cards.
    top_card="main section:first-of-type, main .pv-top-card",
    unavailable_marker=":text('Page not found'), :text('Profile is not available')",
    connect_button="button[aria-label^='Invite'][aria-label$='to connect'], button:has-text('Connect')",
    pending_marker="button:has-text('Pending'), button[aria-label^='Pending']",
    # Read only inside the profile header (top_card), so the top bar's Messaging link can never match. The link's text also holds an icon
    # and hidden screen-reader words, so it is matched by where it goes, not by its exact text. "Message with Premium" is an upsell, not a chat.
    message_button="a[href*='/messaging/compose']:not([aria-label*='Premium']), button[aria-label^='Message ']:not([aria-label*='Premium'])",
    follow_button="button[aria-label^='Follow'], button:has-text('Follow')",
    following_marker="button[aria-label^='Following'], button:has-text('Following')",
    note_toggle="button[aria-label='Add a note']",
    note_input="textarea[name='message']",
    send_invite_button="button[aria-label='Send invitation'], button[aria-label='Send now']",
    invite_limit_marker=":text('weekly invitation limit')",
    note_error="[data-test-note-error]",
    composer_input="div.msg-form__contenteditable, textarea[name='message']",
    composer_send="button.msg-form__send-button",
    sent_body=".msg-s-event-listitem__body",
    conversation_item="li.msg-conversation-listitem",
    conversation_profile_link="a[href*='/in/']",
    thread_message="li.msg-s-message-list__event",
    like_button="button[aria-label^='React Like'], button[aria-label='Like']:not([aria-pressed='true'])",
    liked_marker="button[aria-pressed='true'][aria-label*='Like']",
    no_posts_marker=":text('hasn\\'t posted yet'), :text('No recent activity')",
    inmail_button="button:has-text('InMail'), a:has-text('InMail')",
    inmail_subject="input[name='subject'], input[placeholder*='Subject']",
    inmail_body="div.msg-form__contenteditable, textarea[name='message']",
    inmail_send="button.msg-form__send-button",
    inmail_free_marker=":text('Free message'), :text('Free InMail')",
    inmail_no_credits_marker=":text('out of InMail credits'), :text('no InMail credits')",
    attach_input="input[type='file']",
    attach_send="button.msg-form__send-button",
    reaction_open="button[aria-label^='React Like']",
    reaction_choice="button[aria-label='{name}']",
    reacted_marker="button[aria-pressed='true'][aria-label*='React']",
    comment_box="div.comments-comment-box__form div[contenteditable='true'], div.ql-editor[contenteditable='true']",
    comment_submit="button.comments-comment-box__submit-button, button.comments-comment-box__submit-button--cr",
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
    name: str = ""  # the person's name from the thread header, when the page shows it
    photo: str = ""  # the person's profile photo from the thread header (a LinkedIn image address), when shown


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
        """pending, not_connected or connected, read from this person's own header only."""
        scope = page
        if self.sel.top_card:
            try:
                card = page.locator(self.sel.top_card).first
                if await card.is_visible():
                    scope = card
            except PlaywrightError:
                pass

        async def shows(selector: str) -> bool:
            return await _first_visible(scope.locator(selector)) is not None

        if await shows(self.sel.pending_marker):
            return "pending"
        if await shows(self.sel.message_button) and not await shows(self.sel.connect_button):
            return "connected"
        state = "not_connected" if await shows(self.sel.connect_button) else ("connected" if await shows(self.sel.message_button) else "not_connected")
        if state == "not_connected":
            try:  # only the labels of the header's buttons and links: no names, no message text
                labels = await scope.locator("button, a[role='button'], a[href*='/messaging']").evaluate_all(
                    "els => els.filter(e => e.offsetParent !== null).slice(0, 15).map(e => (e.getAttribute('aria-label') || e.innerText || '').trim().split(' ')[0].slice(0, 20))")
                log.info("connection check read not_connected; header buttons: %s; scoped to header: %s", labels, scope is not page)
            except PlaywrightError:
                pass
        return state

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
        if self.sel.top_card:
            card = page.locator(self.sel.top_card).first
            try:
                # A click made the instant the profile appears does nothing: LinkedIn's page scripts are not attached yet. Let it settle.
                try:
                    await page.wait_for_load_state("networkidle", timeout=8_000)
                except PlaywrightTimeout:
                    pass
                await page.wait_for_timeout(random.randint(1_200, 2_400))
                # Verified on real LinkedIn: the Message link's address is LinkedIn's own message page for this person (a New message page
                # with the box and Send in the page itself). Opening it directly never depends on a click being picked up.
                link = await _first_visible(card.locator(self.sel.message_button))
                href = (await link.get_attribute("href")) if link is not None else None
                if href and "/messaging/compose" in href:
                    await self.goto(page, self._absolute(href))
                    return
                for attempt in range(2):  # a second click only if the chat window did not open after the first
                    target = await _first_visible(card.locator(self.sel.message_button))
                    if not await card.is_visible() or target is None:
                        break
                    await target.hover()
                    await page.wait_for_timeout(random.randint(250, 600))
                    await target.click()
                    if await self.wait_for_composer(page, 5_000) is not None:
                        return
                return
            except PlaywrightError:
                pass
        await self._click_and_settle(page, self.sel.message_button)

    async def wait_for_composer(self, page: Page, timeout_ms: int = 10_000):
        """The on-screen message box of the chat window that Message opened, or None. Only the page's own document is searched:
        the hidden spare copy of the messaging app in the /preload/ frame is never used."""
        waited = 0
        while waited <= timeout_ms:
            box = await _first_visible(page.locator(self.sel.composer_input))
            if box is not None:
                return box
            await page.wait_for_timeout(250)
            waited += 250
        return None

    async def submit_message(self, page: Page, text: str) -> None:
        # Real LinkedIn keeps hidden copies of the message box. Wait for the one on screen, type there, and press its own Send.
        box = await self.wait_for_composer(page, 20_000)
        if box is None:
            raise PlaywrightTimeout("the message box did not open")
        # Type it like a person. LinkedIn's box only registers real key presses: text set in one go leaves Send disabled.
        try:
            await box.click(timeout=4_000)
        except PlaywrightError:  # something covers the box (LinkedIn's floating chat); focus it directly, nothing is lost
            await box.focus(timeout=4_000)
        await box.press_sequentially(text, delay=random.randint(25, 70), timeout=60_000)
        send = None
        for _ in range(20):  # Send turns on once LinkedIn has registered the text
            send = await _first_visible(page.locator(self.sel.composer_send))
            if send is not None and await send.is_enabled():
                break
            await page.wait_for_timeout(250)
        if send is None or not await send.is_enabled():
            raise PlaywrightTimeout("the Send button did not turn on after typing")
        try:
            async with page.expect_navigation(timeout=5_000):
                await send.click()
        except PlaywrightTimeout:
            pass

    async def follow(self, page: Page) -> None:
        await self._click_and_settle(page, self.sel.follow_button)

    async def open_activity(self, page: Page, profile_url: str) -> None:
        await self.goto(page, profile_url.rstrip("/") + "/recent-activity/all/")

    async def has_posts(self, page: Page) -> bool:
        return not await _visible(page, self.sel.no_posts_marker) if self.sel.no_posts_marker else True

    async def first_post_liked(self, page: Page) -> bool:
        return await _visible(page, self.sel.liked_marker)

    async def can_like(self, page: Page) -> bool:
        return await _visible(page, self.sel.like_button)

    async def like_first_post(self, page: Page) -> None:
        await self._click_and_settle(page, self.sel.like_button)

    async def can_open_inmail(self, page: Page) -> bool:
        return await _visible(page, self.sel.inmail_button)

    async def start_inmail(self, page: Page) -> None:
        await self._click_and_settle(page, self.sel.inmail_button)

    async def inmail_is_free(self, page: Page) -> bool:
        return await _visible(page, self.sel.inmail_free_marker)

    async def inmail_out_of_credits(self, page: Page) -> bool:
        return await _visible(page, self.sel.inmail_no_credits_marker)

    async def submit_inmail(self, page: Page, subject: str, body: str) -> None:
        if subject:
            await page.fill(self.sel.inmail_subject, subject)
        await page.fill(self.sel.inmail_body, body)
        await self._click_and_settle(page, self.sel.inmail_send)

    async def attach_and_send_audio(self, page: Page, path: str) -> None:
        await page.set_input_files(self.sel.attach_input, path)
        await self._click_and_settle(page, self.sel.attach_send)

    async def react(self, page: Page, reaction: str) -> None:
        """Open the reaction picker and choose one. For Like, the Like control itself is the reaction."""
        if reaction == "Like":
            await self._click_and_settle(page, self.sel.reaction_open)
            return
        await page.hover(self.sel.reaction_open)
        await self._click_and_settle(page, self.sel.reaction_choice.replace("{name}", reaction))

    async def has_reacted(self, page: Page) -> bool:
        return await _visible(page, self.sel.reacted_marker)

    async def comment(self, page: Page, text: str) -> None:
        await page.fill(self.sel.comment_box, text)
        await self._click_and_settle(page, self.sel.comment_submit)

    async def withdraw_invite(self, page: Page) -> None:
        """Open the pending invitation and confirm the withdrawal. UNVERIFIED on the real site: the Pending button is clicked, then the last
        button or link that says Withdraw (a menu item, then the confirmation) is clicked."""
        await self._click_and_settle(page, self.sel.pending_marker)
        await self._click_and_settle(page, "button:has-text('Withdraw'), a:has-text('Withdraw')")

    async def last_sent_text(self, page: Page) -> str | None:
        out = page.locator(f"{self.sel.thread_message}[data-direction='out']")
        count = await out.count()
        if count:
            return (await out.nth(count - 1).inner_text()).strip()
        if self.sel.sent_body:  # real LinkedIn: the newest bubble in the open conversation is the one just sent
            for _ in range(40):  # the bubble appears a moment after Send (in the open chat window, not the hidden spare frame)
                try:
                    bodies = page.locator(self.sel.sent_body)
                    n = await bodies.count()
                    if n:
                        return (await bodies.nth(n - 1).inner_text()).strip()
                except PlaywrightError:
                    pass
                await page.wait_for_timeout(250)
        return None

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
    HEADER_PHOTO = "img.presence-entity__image"  # the person's photo in the open chat's header
    EVENT = "li.msg-s-message-list__event"
    BODY = "p.msg-s-event-listitem__body"

    def __init__(self, site: Site, selectors: ProfileSelectors) -> None:
        super().__init__(site, selectors)
        self._cache: dict[str, list[ThreadMessage]] = {}

    async def _messaging(self, page: Page, wait_for: str, timeout_ms: int = 30_000):
        """The document that holds the messaging app: the embedded /preload/ frame on today's LinkedIn, or the page itself
        (the mock site, or LinkedIn if it moves it back). None when neither shows ``wait_for`` in time."""
        waited = 0
        while waited <= timeout_ms:
            for frame in [page.main_frame, *[f for f in page.frames if "/preload" in (f.url or "")]]:
                try:
                    if await frame.locator(wait_for).count():
                        return frame
                except PlaywrightError:
                    continue
            await page.wait_for_timeout(500)
            waited += 500
        return None

    async def list_conversations(self, page: Page, since=None) -> list[ConversationRef]:
        await self.goto(page, self.base_url + "/messaging/")
        root = await self._messaging(page, f"{self.ROW} {self.ROW_LINK}")
        if root is None:
            # The list did not appear at all. Say so instead of reporting an empty inbox, so "last synced" is not moved forward.
            raise PlaywrightTimeout("the LinkedIn conversation list did not load")
        await page.wait_for_timeout(1500)
        rows = root.locator(self.ROW)
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
                await root.wait_for_selector(self.HEADER_LINK, timeout=15_000)
            except Exception:  # noqa: BLE001 - not a one-to-one thread (group, sponsored): skipped
                continue
            await page.wait_for_timeout(1200)
            thread_id = urlsplit(page.url).path.rstrip("/").rsplit("/", 1)[-1]
            header = root.locator(self.HEADER_LINK).first
            href = await header.get_attribute("href")
            if not href or "/in/" not in href:
                continue
            name = ((await header.inner_text()) or "").strip().split("\n")[0].strip()
            if not name:
                match = re.match(r"Open (.+?)[’']s profile", await header.get_attribute("title") or "")
                name = match.group(1) if match else ""
            photo = ""
            try:
                img = root.locator(self.HEADER_PHOTO).first
                if await img.count():
                    src = await img.get_attribute("src") or ""
                    photo = src if src.startswith("https://media.licdn.com/") else ""
            except PlaywrightError:
                pass
            self._cache[thread_id] = await self._read_open_thread(root, href)
            refs.append(ConversationRef(thread_id, self._absolute(href), datetime.now(timezone.utc).isoformat(), name[:120], photo[:1000]))
            await page.wait_for_timeout(random.uniform(2500, 5500))
        return refs

    async def read_thread(self, page: Page, thread_id: str) -> list[ThreadMessage]:
        if thread_id in self._cache:
            return self._cache.pop(thread_id)
        await self.goto(page, f"{self.base_url}/messaging/thread/{thread_id}/")
        root = await self._messaging(page, self.HEADER_LINK, timeout_ms=15_000) or page
        href = await root.locator(self.HEADER_LINK).first.get_attribute("href")
        return await self._read_open_thread(root, href or "")

    async def _read_open_thread(self, page, other_href: str) -> list[ThreadMessage]:
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
