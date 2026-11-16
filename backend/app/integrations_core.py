"""Integrations: API keys, outgoing webhooks (and Slack), notification emails, and the usage meter.

Everything here works with no paid service. Webhooks are sent from this server, signed so the receiver can check them. Notification emails go through SMTP
when it is configured and are always written to the outbox table, so they can be read in the app when it is not.
"""
from __future__ import annotations

import hashlib
import hmac
import http.client
import ipaddress
import json
import logging
import secrets
import smtplib
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timezone
from email.message import EmailMessage
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from . import models
from .config import settings
from .database import SessionLocal

log = logging.getLogger("synex.integrations")

EVENTS = {
    "reply_received": "A lead replied",
    "connection_accepted": "A connection request was accepted",
    "campaign_launched": "A campaign was launched",
    "campaign_paused": "A campaign was paused",
    "account_connected": "A sender account was connected",
    "account_disconnected": "A sender account was disconnected",
    "lead_interested": "A conversation was marked interested",
}
KEY_PREFIX = "syx_"


# ---- API keys ----------------------------------------------------------------------------------------------------------

SCOPES = ("read", "write")
RATE_PER_MINUTE = 60  # requests per key per minute on the public API and MCP
_hits: dict[str, deque] = {}
_hits_lock = threading.Lock()


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def create_api_key(db: Session, user_id: str, name: str, scopes: list[str] | None = None) -> tuple[models.ApiKey, str]:
    """The full key is returned once; only its hash is stored. A key can read, and can write only when it was made with that scope."""
    chosen = [s for s in SCOPES if s in (scopes or ["read"])] or ["read"]
    key = KEY_PREFIX + secrets.token_urlsafe(32)
    row = models.ApiKey(user_id=user_id, name=name.strip()[:80] or "API key", prefix=key[:12], key_hash=_hash(key), scopes=chosen)
    db.add(row)
    db.flush()
    return row, key


def key_scopes(row: models.ApiKey) -> set[str]:
    """Keys made before scopes existed are read-only: the safer reading of no scope recorded."""
    return set(row.scopes) if row.scopes else {"read"}


def authenticate(db: Session, key: str | None) -> models.ApiKey | None:
    """The key's row when it is valid and not revoked, and note when it was last used."""
    if not key or not key.startswith(KEY_PREFIX):
        return None
    row = db.query(models.ApiKey).filter_by(key_hash=_hash(key)).first()
    if row is None or row.revoked_at is not None:
        return None
    row.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return row


def user_for_key(db: Session, key: str | None) -> models.User | None:
    row = authenticate(db, key)
    return db.get(models.User, row.user_id) if row else None


def retry_after(key_id: str, now: float | None = None) -> int:
    """0 when this request is allowed (and counted); otherwise the seconds to wait. A sliding one-minute window per key."""
    now = time.monotonic() if now is None else now
    with _hits_lock:
        window = _hits.setdefault(key_id, deque())
        while window and now - window[0] >= 60:
            window.popleft()
        if len(window) >= RATE_PER_MINUTE:
            return max(1, int(60 - (now - window[0])) + 1)
        window.append(now)
        return 0


# ---- webhooks ----------------------------------------------------------------------------------------------------------

def _blocked(ip) -> bool:
    """Anything that is not a public internet address: private, loopback, link-local, carrier-grade NAT, multicast, reserved, unspecified."""
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return not ip.is_global or ip.is_multicast


def resolve_public(host: str, port: int) -> str:
    """The first address of the host, refusing it when ANY of its addresses is not public. Raises OSError (not found) or PermissionError (private)."""
    infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    addresses = [ipaddress.ip_address(info[4][0]) for info in infos]
    if not addresses or any(_blocked(ip) for ip in addresses):
        raise PermissionError("private")
    return str(addresses[0])


def check_webhook_url(url: str, kind: str = "webhook") -> str | None:
    """Why a webhook address is refused, or None. Private and local addresses are refused unless ALLOW_PRIVATE_WEBHOOKS is set (for testing)."""
    parts = urlsplit((url or "").strip())
    if parts.scheme not in ("https", "http") or not parts.hostname:
        return "Enter a full address starting with https://."
    if parts.username or parts.password:
        return "Leave the username and password out of the address."
    if kind == "slack" and parts.hostname != "hooks.slack.com":
        return "A Slack webhook address starts with https://hooks.slack.com/."
    if parts.scheme == "http" and not settings.allow_private_webhooks:
        return "Use https:// so the data is encrypted on the way."
    if not settings.allow_private_webhooks:
        try:
            resolve_public(parts.hostname, parts.port or 443)
        except PermissionError:
            return "That address points to a private network, which Synex will not call."
        except OSError:
            return "That address could not be found."
    return None


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect could point at a private address that was never checked, so none is followed."""

    def redirect_request(self, *args, **kwargs):
        return None


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connects to the address that was just checked (not a second DNS answer) while still verifying the certificate for the real host name."""
    pinned_ip = ""

    def connect(self):
        sock = socket.create_connection((self.pinned_ip, self.port), self.timeout)
        self.sock = ssl.create_default_context().wrap_socket(sock, server_hostname=self.host)


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, ip: str):
        super().__init__()
        self.ip = ip

    def https_open(self, req):
        def factory(host, **kwargs):
            connection = _PinnedHTTPSConnection(host, **kwargs)
            connection.pinned_ip = self.ip
            return connection
        return self.do_open(factory, req)


TIMEOUT_SECONDS = 10
MAX_ATTEMPTS = 3
RETRY_DELAYS = (0, 2, 6)  # seconds before attempt 1, 2 and 3


def _post(hook: models.Webhook, event: str, data: dict) -> tuple[int | None, str | None]:
    """One delivery attempt. The address is checked again now, redirects are refused, and the call ends after TIMEOUT_SECONDS."""
    if hook.kind == "slack":
        payload = {"text": f"*Synex*: {EVENTS.get(event, event)}" + (f" ({data.get('name')})" if data.get("name") else "")}
    else:
        payload = {"event": event, "createdAt": datetime.now(timezone.utc).isoformat(), "data": data}
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "User-Agent": "Synex-Webhook"}
    if hook.kind != "slack":
        headers["X-Synex-Signature"] = sign(hook.secret, body)
        headers["X-Synex-Event"] = event
    problem = check_webhook_url(hook.url, hook.kind)
    if problem:
        return None, "Not sent: " + problem
    handlers: list = [_NoRedirect()]
    parts = urlsplit(hook.url)
    if not settings.allow_private_webhooks:
        try:
            handlers.append(_PinnedHTTPSHandler(resolve_public(parts.hostname, parts.port or 443)))
        except (OSError, PermissionError):
            return None, "Not sent: that address is not a public address."
    request = urllib.request.Request(hook.url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.build_opener(*handlers).open(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - address checked just above
            return response.status, None
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400:
            return exc.code, "The receiver tried to redirect the request. Synex does not follow redirects."
        return exc.code, f"The receiver answered {exc.code}."
    except Exception as exc:  # noqa: BLE001 - recorded by type only
        return None, f"Could not reach the receiver ({type(exc).__name__})."


def _worth_retrying(status: int | None) -> bool:
    return status is None or status >= 500 or status == 429


def deliver(hook_id: str, event: str, data: dict) -> None:
    """Send one event, up to MAX_ATTEMPTS tries for a network failure or a 5xx/429 answer, and record every attempt. No database session is open while waiting or calling."""
    for attempt in range(MAX_ATTEMPTS):
        if RETRY_DELAYS[attempt]:
            time.sleep(RETRY_DELAYS[attempt])
        with SessionLocal() as db:
            hook = db.get(models.Webhook, hook_id)
            if hook is None or not hook.enabled:
                return
            detached = models.Webhook(id=hook.id, kind=hook.kind, url=hook.url, secret=hook.secret)
        status, error = _post(detached, event, data)
        with SessionLocal() as db:
            db.add(models.WebhookDelivery(webhook_id=hook_id, event=event, status_code=status, error=error, ok=bool(status and 200 <= status < 300)))
            db.commit()
        if not _worth_retrying(status):
            return


def emit(db: Session, user_id: str, event: str, data: dict) -> int:
    """Queue an event for every enabled webhook of the workspace that listens to it, and note it for notification emails. Never raises into the caller."""
    started = 0
    try:
        for hook in db.query(models.Webhook).filter_by(user_id=user_id, enabled=True).all():
            if event in (hook.events or []):
                threading.Thread(target=deliver, args=(hook.id, event, data), daemon=True, name="webhook").start()
                started += 1
        notify(db, user_id, event, data)
    except Exception:  # noqa: BLE001
        log.exception("emitting %s failed", event)
    return started


# ---- notification emails -----------------------------------------------------------------------------------------------

NOTIFY_DEFAULTS = {"emails": [], "account_connected": True, "account_disconnected": True, "reply_received": False, "campaign_paused": True, "campaign_launched": False}


def notification_settings(db: Session, user_id: str) -> dict:
    row = db.get(models.WorkspaceSetting, (user_id, "notifications"))
    return {**NOTIFY_DEFAULTS, **(row.value if row else {})}


def check_notification_settings(value: dict) -> dict:
    import re
    out = dict(NOTIFY_DEFAULTS)
    emails = value.get("emails", [])
    if not isinstance(emails, list) or len(emails) > 10 or any(not isinstance(e, str) or not re.fullmatch(r"[^@\s]{1,64}@[^@\s]{1,200}\.[^@\s]{2,}", e.strip()) for e in emails):
        raise ValueError("Give up to 10 valid email addresses.")
    out["emails"] = [e.strip().lower() for e in emails]
    for key in NOTIFY_DEFAULTS:
        if key != "emails" and key in value:
            if not isinstance(value[key], bool):
                raise ValueError(f"{key}: on or off.")
            out[key] = value[key]
    return out


def send_mail(db: Session, user_id: str, to: str, subject: str, body: str) -> str:
    """Write the email to the outbox and send it when SMTP is configured. Returns 'sent' or 'stored'."""
    status = "stored"
    if settings.smtp_host:
        try:
            msg = EmailMessage()
            msg["From"], msg["To"], msg["Subject"] = settings.smtp_from or "synex@localhost", to, subject
            msg.set_content(body)
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
                smtp.starttls()
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(msg)
            status = "sent"
        except Exception as exc:  # noqa: BLE001
            status = f"failed: {type(exc).__name__}"
    db.add(models.OutboxEmail(user_id=user_id, to_address=to, subject=subject[:200], body=body[:5000], status=status))
    return status


def notify(db: Session, user_id: str, event: str, data: dict) -> int:
    cfg = notification_settings(db, user_id)
    if not cfg["emails"] or not cfg.get(event):
        return 0
    subject = f"Synex: {EVENTS.get(event, event)}"
    body = f"{EVENTS.get(event, event)}.\n" + "\n".join(f"{k}: {v}" for k, v in data.items() if k in ("name", "campaign", "account", "lead", "reason"))
    for address in cfg["emails"]:
        send_mail(db, user_id, address, subject, body)
    db.flush()  # the caller commits with the rest of its work
    return len(cfg["emails"])


# ---- usage meter -------------------------------------------------------------------------------------------------------

def usage(db: Session, user_id: str) -> dict:
    """What this workspace has used. Replaces credits: nothing is bought, so this is a meter, not a balance."""
    from datetime import timedelta

    from sqlalchemy import func

    from .assistant.service import used_seconds
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)
    by_type = dict(db.query(models.AgentTask.type, func.count()).join(models.LinkedInAccount, models.AgentTask.account_id == models.LinkedInAccount.id)
                   .filter(models.LinkedInAccount.user_id == user_id, models.AgentTask.status == "done", models.AgentTask.created_at >= since).group_by(models.AgentTask.type).all())
    month = now.strftime("%Y-%m")
    drafts = db.query(models.LeadDraft).filter(models.LeadDraft.user_id == user_id, models.LeadDraft.source.in_(["ai", "edited"]), models.LeadDraft.created_at >= datetime(now.year, now.month, 1, tzinfo=timezone.utc)).count()
    return {"actionsLast24h": by_type, "aiDraftsThisMonth": drafts, "assistantMinutesThisMonth": round(used_seconds(db, user_id) / 60, 1), "month": month,
            "leads": db.query(models.Lead).filter_by(user_id=user_id).count(), "campaigns": db.query(models.Campaign).filter_by(user_id=user_id).count(),
            "seatsUsed": db.query(models.LinkedInAccount).filter(models.LinkedInAccount.user_id == user_id, models.LinkedInAccount.status.notin_(["deleted", "deactivated"])).count(),
            "note": "Synex does not sell credits or plans yet, so this is a meter of what you used, not a balance."}
