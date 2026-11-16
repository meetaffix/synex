"""Integrations: API keys, outgoing webhooks (and Slack), notification emails, and the usage meter.

Everything here works with no paid service. Webhooks are sent from this server, signed so the receiver can check them. Notification emails go through SMTP
when it is configured and are always written to the outbox table, so they can be read in the app when it is not.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import smtplib
import socket
import threading
import urllib.error
import urllib.request
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

def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def create_api_key(db: Session, user_id: str, name: str) -> tuple[models.ApiKey, str]:
    """The full key is returned once; only its hash is stored."""
    key = KEY_PREFIX + secrets.token_urlsafe(32)
    row = models.ApiKey(user_id=user_id, name=name.strip()[:80] or "API key", prefix=key[:12], key_hash=_hash(key))
    db.add(row)
    db.flush()
    return row, key


def user_for_key(db: Session, key: str | None) -> models.User | None:
    if not key or not key.startswith(KEY_PREFIX):
        return None
    row = db.query(models.ApiKey).filter_by(key_hash=_hash(key)).first()
    if row is None or row.revoked_at is not None:
        return None
    row.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return db.get(models.User, row.user_id)


# ---- webhooks ----------------------------------------------------------------------------------------------------------

def check_webhook_url(url: str, kind: str = "webhook") -> str | None:
    """Why a webhook address is refused, or None. Private and local addresses are refused unless ALLOW_PRIVATE_WEBHOOKS is set (for testing)."""
    parts = urlsplit((url or "").strip())
    if parts.scheme not in ("https", "http") or not parts.hostname:
        return "Enter a full address starting with https://."
    if kind == "slack" and parts.hostname != "hooks.slack.com":
        return "A Slack webhook address starts with https://hooks.slack.com/."
    if parts.scheme == "http" and not settings.allow_private_webhooks:
        return "Use https:// so the data is encrypted on the way."
    if not settings.allow_private_webhooks:
        try:
            for info in socket.getaddrinfo(parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP):
                ip = ipaddress.ip_address(info[4][0])
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    return "That address points to a private network, which Synex will not call."
        except OSError:
            return "That address could not be found."
    return None


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _post(hook: models.Webhook, event: str, data: dict) -> tuple[int | None, str | None]:
    if hook.kind == "slack":
        payload = {"text": f"*Synex*: {EVENTS.get(event, event)}" + (f" ({data.get('name')})" if data.get("name") else "")}
    else:
        payload = {"event": event, "createdAt": datetime.now(timezone.utc).isoformat(), "data": data}
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "User-Agent": "Synex-Webhook"}
    if hook.kind != "slack":
        headers["X-Synex-Signature"] = sign(hook.secret, body)
        headers["X-Synex-Event"] = event
    request = urllib.request.Request(hook.url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - checked by check_webhook_url when saved
            return response.status, None
    except urllib.error.HTTPError as exc:
        return exc.code, f"The receiver answered {exc.code}."
    except Exception as exc:  # noqa: BLE001 - recorded by type only
        return None, f"Could not reach the receiver ({type(exc).__name__})."


def deliver(hook_id: str, event: str, data: dict) -> None:
    """Send one event and record the result. Runs outside any request's database session."""
    with SessionLocal() as db:
        hook = db.get(models.Webhook, hook_id)
        if hook is None or not hook.enabled:
            return
        status, error = _post(hook, event, data)
        db.add(models.WebhookDelivery(webhook_id=hook.id, event=event, status_code=status, error=error, ok=bool(status and 200 <= status < 300)))
        db.commit()


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
