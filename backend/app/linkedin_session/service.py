"""Glue between the HTTP routers and the session manager. All HTTP errors are
raised here as HTTPException so the routers stay thin."""
import threading
import time
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from .manager import Attempt, AttemptActive, CheckFailed, CodeNotExpected, PROXY_REQUIRED_MESSAGE, SessionManager
from .pages import LINKEDIN
from . import proxytest
from .proxytest import proxy_host_allowed
from . import store

_manager: SessionManager | None = None


def get_manager() -> SessionManager:
    """FastAPI dependency; tests override it to inject a manager bound to a mock site."""
    global _manager
    if _manager is None:
        _manager = SessionManager(
            LINKEDIN, max_browsers=settings.effective_max_browsers,
            attempt_timeout=settings.linkedin_session_attempt_timeout_seconds,
            poll_interval=settings.linkedin_session_poll_interval_seconds,
            headless=settings.linkedin_session_headless,
            require_proxy=settings.require_account_proxy,
            capture_dir=Path(settings.linkedin_capture_dir) if settings.linkedin_capture_dir else Path(__file__).resolve().parents[2] / "captures")
    return _manager


def shutdown_manager() -> None:
    global _manager
    if _manager is not None:
        _manager.shutdown()
        _manager = None


def owned_account(db: Session, workspace_id: str, account_id: str) -> models.LinkedInAccount:
    account = db.get(models.LinkedInAccount, account_id)
    if account is None or account.user_id != workspace_id:
        raise HTTPException(404, "LinkedIn account not found")
    return account


def begin_login(manager: SessionManager, db: Session, *, workspace_id: str, account: models.LinkedInAccount | None,
                identifier: str, password: str, proxy_url: str | None = None, timezone: str | None = None,
                token_digest: str | None = None, sync_mode: str | None = None, connected_by: str | None = None) -> Attempt:
    """Start a login. For an existing account the stored identity and proxy are reused."""
    identity = account.browser_profile if account else None
    if account and proxy_url is None:
        proxy_url = store.load_proxy(account)
    try:
        return manager.start_login(
            workspace_id=workspace_id, identifier=identifier, password=password, proxy_url=proxy_url, timezone=timezone,
            identity=identity, target_account_id=account.id if account else None, token_digest=token_digest,
            sync_mode=sync_mode, connected_by=connected_by)
    except AttemptActive:
        raise HTTPException(409, "A connection attempt for this account is already in progress.") from None


def require_sync_owner(account: models.LinkedInAccount, actor_id: str) -> None:
    if not store.can_change_sync_mode(account, actor_id):
        raise HTTPException(403, "Only the person who connected this account can change its sync preference.")


def require_allowed_proxy(proxy_url: str | None) -> None:
    """A proxy on a private or loopback address would make the server connect into its own network."""
    if proxy_url and not proxy_host_allowed(proxy_url):
        raise HTTPException(422, [{"loc": ["body", "proxyUrl"], "type": "proxy.not_allowed",
                                  "msg": proxytest.MESSAGES["proxy_not_allowed"]}])


def attempt_for(manager: SessionManager, attempt_id: str, *, workspace_id: str | None = None,
                token_digest: str | None = None) -> Attempt:
    """Fetch an attempt the caller is allowed to see; anything else is a 404."""
    attempt = manager.get(attempt_id)
    allowed = attempt is not None and (
        attempt.workspace_id == workspace_id if workspace_id is not None else attempt.token_digest == token_digest)
    if not allowed:
        raise HTTPException(404, "Connection attempt not found")
    return attempt


def send_code(manager: SessionManager, attempt: Attempt, code: str) -> None:
    try:
        manager.submit_code(attempt, code)
    except CodeNotExpected:
        raise HTTPException(409, "This connection is not waiting for a verification code.") from None


_CHECK_LOCK = threading.Lock()
_CHECKS: dict[str, float | None] = {}  # account id -> None while a check runs, else when the last one finished
CHECK_COOLDOWN_SECONDS = 30


def _claim_check(account_id: str) -> bool:
    """True when this call may open a browser. A second call while one runs, or within the cooldown after one, is dropped:
    repeated checks of the same session add risk and no information."""
    with _CHECK_LOCK:
        if account_id in _CHECKS:
            finished = _CHECKS[account_id]
            if finished is None or time.monotonic() - finished < CHECK_COOLDOWN_SECONDS:
                return False
        _CHECKS[account_id] = None
        return True


def run_check(manager: SessionManager, account: models.LinkedInAccount) -> None:
    if not _claim_check(account.id):
        return  # the caller returns the account as it stands; the check in flight (or just done) updates it
    try:
        _run_check(manager, account)
    finally:
        with _CHECK_LOCK:
            _CHECKS[account.id] = time.monotonic()


def _run_check(manager: SessionManager, account: models.LinkedInAccount) -> None:
    state = store.load_state(account)
    if state is None or not account.browser_profile:
        raise HTTPException(409, "This account has no saved session. Reconnect it first.")
    if settings.require_account_proxy and not store.load_proxy(account):
        raise HTTPException(409, PROXY_REQUIRED_MESSAGE)
    try:
        result = manager.check_session(storage_state=state, identity=account.browser_profile,
                                       proxy_url=store.load_proxy(account))
    except CheckFailed as exc:
        raise HTTPException(502, str(exc)) from None
    store.record_check(account.id, result.status, result.storage_state, result.profile)
