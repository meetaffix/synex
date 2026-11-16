"""Login state machine and health checks, running on the Playwright thread.

One background task per login attempt:
    starting -> awaiting_code | awaiting_app_approval | awaiting_manual_verification
             -> succeeded | failed
Every attempt closes its browser on success, failure, cancel, timeout and shutdown.
Passwords and codes live only in local variables and are never logged.
"""
import asyncio
import logging
import threading
import time
import uuid
from collections.abc import Awaitable, Callable
from concurrent.futures import Future, TimeoutError as FutureTimeout
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field

from playwright.async_api import Browser, BrowserContext, Page, Playwright, TimeoutError as PlaywrightTimeout, async_playwright

from pathlib import Path
from urllib.parse import urlsplit

from . import store
from .capture import Diagnosis, capture
from .identity import new_identity, parse_proxy
from .pages import Challenge, LoginSite, PageState, Profile
from .runtime import BrowserRuntime

log = logging.getLogger("synex.linkedin_session")

MAX_CODE_REJECTIONS = 3
# A checkpoint page mid-navigation looks unrecognisable; only a stable one needs the user.
MANUAL_VERIFICATION_POLLS = 3
# A page that stays unrecognisable this long is not "still loading": stop instead of waiting out the whole attempt.
PENDING_LIMIT_SECONDS = 90
CHECK_TIMEOUT_SECONDS = 60
RETENTION_SECONDS = 900
STEP_TIMEOUT_MS = 30_000


class AttemptActive(Exception):
    """Another attempt for the same account is still running."""


class CodeNotExpected(Exception):
    """The attempt is not waiting for a verification code."""


PROXY_REQUIRED_MESSAGE = ("This server only connects LinkedIn accounts through a proxy in your own country. "
                          "Add a proxy to this account (Advanced: proxy), then try again.")


class ProxyRequired(Exception):
    """The server requires a proxy for every browser, and this account has none. Nothing was opened."""


class CheckFailed(Exception):
    """A health check could not reach a verdict (network, proxy or timeout)."""


class LoginFailed(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


class ManualVerification(Exception):
    """LinkedIn wants a checkpoint only the user can complete on LinkedIn itself."""


@dataclass
class Attempt:
    id: str
    workspace_id: str
    key: str
    target_account_id: str | None
    token_digest: str | None
    sync_mode: str | None = None
    connected_by: str | None = None
    created_at: float = field(default_factory=time.monotonic)
    state: str = "starting"
    challenge: Challenge | None = None
    error: tuple[str, str] | None = None
    account_id: str | None = None
    finished_at: float | None = None
    cancel_requested: bool = False
    codes: asyncio.Queue = field(default_factory=asyncio.Queue)
    task: asyncio.Task | None = None
    last_state: str | None = None
    diagnosis: Diagnosis | None = None

    @property
    def active(self) -> bool:
        return self.finished_at is None


@dataclass(frozen=True)
class SignedIn:
    profile: Profile
    storage_state: dict
    identity: dict


@dataclass(frozen=True)
class CheckResult:
    status: str
    storage_state: dict | None


class SessionManager:
    def __init__(self, site: LoginSite, *, max_browsers: int, attempt_timeout: float,
                 poll_interval: float, headless: bool, capture_dir: Path | None = None,
                 require_proxy: bool = False) -> None:
        self.site = site
        self._max_browsers, self._attempt_timeout = max_browsers, attempt_timeout
        self._poll, self._headless = poll_interval, headless
        self._capture_dir = capture_dir
        self._require_proxy = require_proxy
        self._runtime = BrowserRuntime()
        self._lock = threading.Lock()
        self._attempts: dict[str, Attempt] = {}
        self._active: dict[str, str] = {}
        # Created and used only on the runtime thread.
        self._playwright: Playwright | None = None
        self._semaphore: asyncio.Semaphore | None = None
        self._browsers: set[Browser] = set()

    @property
    def open_browsers(self) -> int:
        return len(self._browsers)

    # ---- called from request threads -------------------------------------------------

    def start_login(self, *, workspace_id: str, identifier: str, password: str, proxy_url: str | None,
                    timezone: str | None, identity: dict | None, target_account_id: str | None,
                    token_digest: str | None = None, sync_mode: str | None = None,
                    connected_by: str | None = None) -> Attempt:
        key = target_account_id or f"new:{workspace_id}:{identifier.lower()}"
        attempt = Attempt(id=uuid.uuid4().hex, workspace_id=workspace_id, key=key,
                          target_account_id=target_account_id, token_digest=token_digest,
                          sync_mode=sync_mode, connected_by=connected_by)
        with self._lock:
            self._prune()
            if key in self._active:
                raise AttemptActive
            self._active[key] = attempt.id
            self._attempts[attempt.id] = attempt
        self._runtime.start()
        self._runtime.submit(self._run(attempt, identifier, password, proxy_url, timezone, identity))
        return attempt

    def get(self, attempt_id: str) -> Attempt | None:
        with self._lock:
            self._prune()
            return self._attempts.get(attempt_id)

    def submit_code(self, attempt: Attempt, code: str) -> None:
        with self._lock:
            if attempt.state != "awaiting_code":
                raise CodeNotExpected
            attempt.state = "starting"  # also rejects a duplicate submission
        self._runtime.call_soon(attempt.codes.put_nowait, code)

    def cancel(self, attempt: Attempt) -> None:
        if not attempt.active:
            return
        attempt.cancel_requested = True
        self._runtime.call_soon(lambda: attempt.task and attempt.task.cancel())

    def cancel_for_account(self, account_id: str) -> None:
        with self._lock:
            attempts = [self._attempts[i] for k, i in self._active.items() if k == account_id]
        for attempt in attempts:
            self.cancel(attempt)

    def check_session(self, *, storage_state: dict, identity: dict, proxy_url: str | None) -> CheckResult:
        self._runtime.start()
        future = self._runtime.submit(self._check(storage_state, identity, proxy_url))
        try:
            return future.result(timeout=CHECK_TIMEOUT_SECONDS + 5)
        except FutureTimeout:
            future.cancel()
            raise CheckFailed("LinkedIn did not respond in time.") from None

    def submit_session_work(self, *, storage_state: dict, identity: dict, proxy_url: str | None,
                            work: Callable[[Page, BrowserContext], Awaitable[None]]) -> Future[None]:
        """Run ``work`` in a saved account session. One browser per call, counted against
        the global browser cap and closed when ``work`` returns or fails."""
        self._runtime.start()
        return self._runtime.submit(self._with_session(storage_state, identity, proxy_url, work))

    def shutdown(self) -> None:
        if not self._runtime.running:
            return
        with suppress(Exception):
            self._runtime.submit(self._shutdown()).result(timeout=20)
        self._runtime.stop()

    # ---- runtime thread --------------------------------------------------------------

    def _prune(self) -> None:
        cutoff = time.monotonic() - RETENTION_SECONDS
        for attempt_id in [i for i, a in self._attempts.items() if a.finished_at and a.finished_at < cutoff]:
            del self._attempts[attempt_id]

    def _set_state(self, attempt: Attempt, state: str) -> None:
        attempt.state = state
        log.info("linkedin login attempt %s -> %s", attempt.id, state)

    def _fail(self, attempt: Attempt, code: str, message: str) -> None:
        if attempt.diagnosis and code in ("unknown", "timeout"):
            message = f"{message} LinkedIn showed: {attempt.diagnosis.label}."
        attempt.challenge, attempt.error = None, (code, message)
        self._set_state(attempt, "failed")
        log.info("linkedin login attempt %s failed: %s", attempt.id, code)

    def _finish(self, attempt: Attempt) -> None:
        with self._lock:
            attempt.finished_at = time.monotonic()
            self._active.pop(attempt.key, None)

    async def _run(self, attempt: Attempt, identifier: str, password: str, proxy_url: str | None,
                   timezone: str | None, identity: dict | None) -> None:
        attempt.task = asyncio.current_task()
        try:
            if attempt.cancel_requested:
                raise asyncio.CancelledError
            async with asyncio.timeout(self._attempt_timeout):
                async with self._slot():
                    signed_in = await self._login(attempt, identifier, password, proxy_url, timezone, identity)
                await self._conclude(attempt, signed_in, identifier, proxy_url)
        except TimeoutError:
            self._fail(attempt, "timeout", "Login did not finish in time. Try again.")
        except asyncio.CancelledError:
            self._fail(attempt, "cancelled", "The connection attempt was cancelled.")
            if not attempt.cancel_requested:
                raise  # application shutdown
        except ProxyRequired:
            self._fail(attempt, "proxy_required", PROXY_REQUIRED_MESSAGE)
        except ManualVerification:
            attempt.challenge = None
            self._set_state(attempt, "awaiting_manual_verification")
        except LoginFailed as exc:
            self._fail(attempt, exc.code, exc.message)
        except Exception as exc:  # noqa: BLE001 - classified below; only the type is logged
            log.warning("linkedin login attempt %s error: %s", attempt.id, type(exc).__name__)
            if self.site.is_proxy_error(exc):
                self._fail(attempt, "proxy_error", "The proxy could not be reached. Check the proxy settings.")
            elif isinstance(exc, PlaywrightTimeout):
                self._fail(attempt, "timeout", "LinkedIn did not respond in time. Try again.")
            else:
                self._fail(attempt, "unknown", "Something went wrong while connecting. Try again.")
        finally:
            await self._count_token_failure(attempt)
            self._finish(attempt)

    async def _count_token_failure(self, attempt: Attempt) -> None:
        if attempt.token_digest and attempt.target_account_id and attempt.state == "failed" and attempt.error and attempt.error[0] != "cancelled":
            with suppress(Exception):
                await asyncio.to_thread(store.record_token_failure, attempt.target_account_id, attempt.token_digest)

    @asynccontextmanager
    async def _slot(self):
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_browsers)
        async with self._semaphore:
            yield

    @asynccontextmanager
    async def _browser(self, identity: dict | None, timezone: str | None, proxy_url: str | None,
                       storage_state: dict | None):
        if self._require_proxy and not proxy_url:  # the single place every browser is launched: nothing opens without a proxy
            log.warning("browser refused: this server requires a proxy and the account has none")
            raise ProxyRequired
        if self._playwright is None:
            self._playwright = await async_playwright().start()
        launch: dict = {"headless": self._headless}
        if proxy_url:
            launch["proxy"] = parse_proxy(proxy_url)
        browser = await self._playwright.chromium.launch(**launch)
        self._browsers.add(browser)
        try:
            identity = identity or new_identity(browser.version, timezone)
            context: BrowserContext = await browser.new_context(
                user_agent=identity["userAgent"], viewport=identity["viewport"], locale=identity["locale"],
                timezone_id=identity["timezoneId"], storage_state=storage_state)
            page = await context.new_page()
            page.set_default_timeout(STEP_TIMEOUT_MS)
            yield identity, context, page
        finally:
            self._browsers.discard(browser)
            with suppress(Exception):
                await browser.close()
            log.info("linkedin browser closed (%d still open)", len(self._browsers))

    async def _login(self, attempt: Attempt, identifier: str, password: str, proxy_url: str | None,
                     timezone: str | None, identity: dict | None) -> "SignedIn":
        async with self._browser(identity, timezone, proxy_url, None) as (used_identity, context, page):
            stage = "sign-in"
            try:
                await self.site.open_login(page)
                await self._drive(attempt, page, identifier, password)
                stage = "profile"
                profile = await self.site.read_profile(page)
            except (LoginFailed, ManualVerification, PlaywrightTimeout, asyncio.CancelledError) as exc:
                force = "profile_not_read" if stage == "profile" else ("navigation_failed" if isinstance(exc, PlaywrightTimeout) and not attempt.last_state else None)
                await self._record(attempt, page, force)
                raise
            except Exception as exc:  # noqa: BLE001 - a proxy or network error still gets its page recorded, then is re-raised as is
                await self._record(attempt, page, "proxy_error" if self.site.is_proxy_error(exc) else ("profile_not_read" if stage == "profile" else None))
                raise
            return SignedIn(profile, await context.storage_state(), used_identity)

    async def _record(self, attempt: Attempt, page: Page, force: str | None) -> None:
        """Classify and screenshot what the browser is looking at. Never raises and never delays a failure by more than 10 s."""
        try:
            attempt.diagnosis = await asyncio.wait_for(
                asyncio.shield(capture(self.site, page, self._capture_dir, attempt.id, attempt.last_state, force)), 10)
            log.info("linkedin login attempt %s capture: %s", attempt.id, attempt.diagnosis.as_log())
        except BaseException:  # noqa: BLE001 - includes cancellation: the original failure is what must propagate
            pass

    async def _conclude(self, attempt: Attempt, signed_in: "SignedIn", identifier: str, proxy_url: str | None) -> None:
        """Save the session. An account's browser identity is fixed at its first connect: when this login
        belongs to an account that already has one, the session is proven under that identity first."""
        storage_state, identity = signed_in.storage_state, signed_in.identity
        stored = await asyncio.to_thread(store.stored_identity, attempt.workspace_id, attempt.target_account_id, signed_in.profile.url)
        if stored and stored != identity:
            try:
                verdict = await self._check(storage_state, stored, proxy_url)
            except CheckFailed:
                raise LoginFailed("unknown", "Signed in, but the session could not be confirmed with this account's saved browser settings. Try again.") from None
            if verdict.status != "connected":
                raise LoginFailed("unknown", "Signed in, but the session could not be confirmed with this account's saved browser settings. Try again.")
            storage_state, identity = verdict.storage_state or storage_state, stored
        try:
            attempt.account_id = await asyncio.to_thread(
                store.save_session, workspace_id=attempt.workspace_id, target_account_id=attempt.target_account_id,
                identifier=identifier, profile=signed_in.profile, storage_state=storage_state, identity=identity,
                proxy_url=proxy_url, sync_mode=attempt.sync_mode, connected_by=attempt.connected_by)
        except store.ProfileMismatch:
            raise LoginFailed("unknown", "That login belongs to a different LinkedIn profile than this account.") from None
        except LookupError:
            raise LoginFailed("unknown", "This account was removed while connecting.") from None
        attempt.challenge = attempt.error = None
        self._set_state(attempt, "succeeded")

    async def _drive(self, attempt: Attempt, page: Page, identifier: str, password: str) -> None:
        submitted, rejections, unrecognised = False, 0, 0
        pending_since = None
        while True:
            state = await self.site.detect_state(page)
            if state.value != attempt.last_state:  # what the browser is looking at: never the query string or a typed value
                attempt.last_state = state.value
                log.info("linkedin login attempt %s page state: %s (path %s)", attempt.id, state.value, urlsplit(page.url).path)
            if state is PageState.PENDING:
                pending_since = pending_since or time.monotonic()
                if time.monotonic() - pending_since > PENDING_LIMIT_SECONDS:
                    raise LoginFailed("unknown", "LinkedIn showed a page Synex could not recognise. Nothing was saved.")
            else:
                pending_since = None
            unrecognised = unrecognised + 1 if state is PageState.MANUAL_VERIFICATION else 0
            if state is PageState.LOGGED_IN:
                return
            if state is PageState.LOGIN_FORM and not submitted:
                await self.site.submit_credentials(page, identifier, password)
                submitted = True
                continue
            if state is PageState.WRONG_CREDENTIALS:
                raise LoginFailed("invalid_credentials", "LinkedIn did not accept that email, phone number or password.")
            if unrecognised >= MANUAL_VERIFICATION_POLLS:
                raise ManualVerification
            if state is PageState.RESTRICTED:
                raise LoginFailed("unknown", "LinkedIn reports this account is restricted. Resolve it on LinkedIn, then connect again.")
            if state in (PageState.CODE_CHALLENGE, PageState.CODE_REJECTED):
                rejections += state is PageState.CODE_REJECTED
                if rejections >= MAX_CODE_REJECTIONS:
                    raise LoginFailed("invalid_credentials", "The verification code was rejected too many times.")
                await self._ask_for_code(attempt, page, rejected=state is PageState.CODE_REJECTED)
                continue
            if state is PageState.APP_APPROVAL:
                self._set_state_once(attempt, "awaiting_app_approval")
            await asyncio.sleep(self._poll)

    def _set_state_once(self, attempt: Attempt, state: str) -> None:
        if attempt.state != state:
            self._set_state(attempt, state)

    async def _ask_for_code(self, attempt: Attempt, page: Page, rejected: bool) -> None:
        while not attempt.codes.empty():
            attempt.codes.get_nowait()
        attempt.error = ("invalid_credentials", "That code was not accepted. Enter a new code.") if rejected else None
        attempt.challenge = await self.site.read_challenge(page)
        self._set_state(attempt, "awaiting_code")
        code = await attempt.codes.get()
        attempt.challenge = None
        await self.site.submit_code(page, code)

    async def _with_session(self, storage_state: dict, identity: dict, proxy_url: str | None,
                            work: Callable[[Page, BrowserContext], Awaitable[None]]) -> None:
        async with self._slot():
            async with self._browser(identity, None, proxy_url, storage_state) as (_, context, page):
                await work(page, context)

    async def _check(self, storage_state: dict, identity: dict, proxy_url: str | None) -> CheckResult:
        try:
            async with asyncio.timeout(CHECK_TIMEOUT_SECONDS), self._slot():
                async with self._browser(identity, None, proxy_url, storage_state) as (_, context, page):
                    await self.site.open_feed(page)
                    state = await self._settled_state(page)
                    if state is PageState.LOGGED_IN:
                        return CheckResult("connected", await context.storage_state())
                    if state is PageState.RESTRICTED:
                        return CheckResult("restricted", None)
                    if state is PageState.PENDING:
                        raise CheckFailed("LinkedIn did not respond. Try again shortly.")
                    return CheckResult("needs_reconnect", None)
        except TimeoutError:
            raise CheckFailed("LinkedIn did not respond in time.") from None
        except CheckFailed:
            raise
        except ProxyRequired:
            raise CheckFailed(PROXY_REQUIRED_MESSAGE) from None
        except Exception as exc:  # noqa: BLE001
            log.warning("linkedin session check error: %s", type(exc).__name__)
            if self.site.is_proxy_error(exc):
                raise CheckFailed("The proxy could not be reached. Check the proxy settings.") from None
            raise CheckFailed("LinkedIn could not be reached. Try again shortly.") from None

    async def _settled_state(self, page: Page) -> PageState:
        for _ in range(20):
            state = await self.site.detect_state(page)
            if state is not PageState.PENDING:
                return state
            await asyncio.sleep(self._poll)
        return PageState.PENDING

    async def _shutdown(self) -> None:
        tasks = [a.task for a in list(self._attempts.values()) if a.task and not a.task.done()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for browser in list(self._browsers):
            with suppress(Exception):
                await browser.close()
        self._browsers.clear()
        if self._playwright:
            with suppress(Exception):
                await self._playwright.stop()
            self._playwright = None
