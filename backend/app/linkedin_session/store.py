"""Persistence for browser sessions. Secrets are Fernet-encrypted; passwords,
codes and raw cookies are never stored in plain text."""
import json
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from .. import models
from ..database import SessionLocal
from ..security import decrypt_secret, encrypt_secret
from ..sessions import aware, digest
from .pages import Profile

RECONNECT_TOKEN_TTL = timedelta(hours=24)
MAX_TOKEN_FAILURES = 5


class ProfileMismatch(Exception):
    """The login belongs to a different LinkedIn profile than the account being reconnected."""


def normalize_profile_url(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}".rstrip("/").lower()


def can_change_sync_mode(account: models.LinkedInAccount, actor_id: str) -> bool:
    """Only whoever connected the account may change it; legacy rows fall back to the workspace owner."""
    return (account.connected_by_user_id or account.user_id) == actor_id


def apply_status(account: models.LinkedInAccount, session_status: str) -> None:
    account.session_status = session_status
    if account.status != "paused":
        account.status = "active" if session_status == "connected" else "pending"


def load_state(account: models.LinkedInAccount) -> dict | None:
    if not account.session_state_encrypted:
        return None
    return json.loads(decrypt_secret(account.session_state_encrypted))


def load_proxy(account: models.LinkedInAccount) -> str | None:
    return decrypt_secret(account.proxy_url_encrypted) if account.proxy_url_encrypted else None


def save_session(*, workspace_id: str, target_account_id: str | None, identifier: str, profile: Profile,
                 storage_state: dict, identity: dict, proxy_url: str | None,
                 sync_mode: str | None = None, connected_by: str | None = None) -> str:
    """Create or update the account after a verified login; returns its id.

    A login that lands on a different profile than ``target_account_id`` is rejected,
    so a reconnect link can never attach a foreign LinkedIn identity.
    """
    url = normalize_profile_url(profile.url)
    with SessionLocal() as db:
        if target_account_id:
            account = db.get(models.LinkedInAccount, target_account_id)
            if account is None or account.user_id != workspace_id:
                raise LookupError("account no longer exists")
            if account.linkedin_url and normalize_profile_url(account.linkedin_url) != url:
                raise ProfileMismatch
        else:
            # Same profile connected again: update it instead of creating a duplicate.
            account = next((a for a in db.query(models.LinkedInAccount).filter_by(user_id=workspace_id)
                            if a.linkedin_url and normalize_profile_url(a.linkedin_url) == url), None)
        if account is None:
            account = models.LinkedInAccount(user_id=workspace_id, name=profile.name)
            db.add(account)
        now = datetime.now(timezone.utc)
        account.name, account.headline, account.linkedin_url = profile.name, profile.headline, url
        account.avatar_url, account.login_identifier = profile.avatar_url, identifier.lower()
        if "@" in identifier:
            account.email = identifier.lower()
        if sync_mode is not None:
            account.sync_mode = sync_mode
        elif account.sync_mode is None:
            account.sync_mode = "synex_only"
        if account.connected_by_user_id is None:
            account.connected_by_user_id = connected_by
        account.session_state_encrypted = encrypt_secret(json.dumps(storage_state))
        account.browser_profile = account.browser_profile or identity  # fixed at first connect, never overwritten
        if proxy_url is not None:
            account.proxy_url_encrypted = encrypt_secret(proxy_url)
        account.connected_at = account.last_checked_at = now
        account.reconnect_token_digest = account.reconnect_token_expires_at = None
        account.reconnect_token_failures = 0
        account.paused_reason = None
        apply_status(account, "connected")
        db.flush()
        from .. import integrations_core  # a webhook or an email tells the workspace the sender is connected (never raises into the login)
        integrations_core.emit(db, workspace_id, "account_connected", {"name": account.name, "account": account.name})
        db.commit()
        return account.id


def record_check(account_id: str, status: str, storage_state: dict | None) -> None:
    with SessionLocal() as db:
        account = db.get(models.LinkedInAccount, account_id)
        if account is None:
            return
        apply_status(account, status)
        account.last_checked_at = datetime.now(timezone.utc)
        if storage_state is not None:
            account.session_state_encrypted = encrypt_secret(json.dumps(storage_state))
        db.commit()


def save_state(account_id: str, storage_state: dict) -> None:
    """Persist refreshed cookies after a batch of actions."""
    with SessionLocal() as db:
        account = db.get(models.LinkedInAccount, account_id)
        if account is not None and account.session_status == "connected":
            account.session_state_encrypted = encrypt_secret(json.dumps(storage_state))
            db.commit()


def wipe_session(db: Session, account: models.LinkedInAccount) -> None:
    account.session_state_encrypted = None
    account.reconnect_token_digest = account.reconnect_token_expires_at = None
    apply_status(account, "disconnected")


def record_token_failure(account_id: str, token_digest: str) -> None:
    """Count a failed sign-in made through a reconnect link; the link dies at the cap."""
    with SessionLocal() as db:
        account = db.get(models.LinkedInAccount, account_id)
        if account is None or account.reconnect_token_digest != token_digest:
            return
        account.reconnect_token_failures = (account.reconnect_token_failures or 0) + 1
        if account.reconnect_token_failures >= MAX_TOKEN_FAILURES:
            account.reconnect_token_digest = account.reconnect_token_expires_at = None
            account.reconnect_token_failures = 0
        db.commit()


def stored_identity(workspace_id: str, target_account_id: str | None, profile_url: str) -> dict | None:
    """The browser identity already fixed for the account this login belongs to, if any."""
    url = normalize_profile_url(profile_url)
    with SessionLocal() as db:
        account = db.get(models.LinkedInAccount, target_account_id) if target_account_id else next(
            (a for a in db.query(models.LinkedInAccount).filter_by(user_id=workspace_id)
             if a.linkedin_url and normalize_profile_url(a.linkedin_url) == url), None)
        return dict(account.browser_profile) if account is not None and account.browser_profile else None


def issue_reconnect_token(db: Session, account: models.LinkedInAccount) -> tuple[str, datetime]:
    """Replace any earlier link: an account has at most one outstanding token."""
    token = secrets.token_urlsafe(32)
    account.reconnect_token_digest = digest(token)
    account.reconnect_token_failures = 0
    account.reconnect_token_expires_at = datetime.now(timezone.utc) + RECONNECT_TOKEN_TTL
    db.commit()
    return token, account.reconnect_token_expires_at


def account_for_token(db: Session, token: str) -> models.LinkedInAccount | None:
    account = db.query(models.LinkedInAccount).filter_by(reconnect_token_digest=digest(token)).first()
    expires = aware(account.reconnect_token_expires_at) if account else None
    return account if expires and expires > datetime.now(timezone.utc) else None
