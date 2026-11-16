"""Workspace settings, monthly usage and the single-use tickets that start a relay session."""
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .config import assistant_config
from .models import AssistantSettings, AssistantUsage


def month_key(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m")


def get_settings_row(db: Session, workspace_id: str) -> AssistantSettings:
    row = db.get(AssistantSettings, workspace_id)
    if row is None:
        row = AssistantSettings(
            workspace_id=workspace_id,
            enabled=True,
            monthly_minute_cap=assistant_config.assistant_default_monthly_minutes,
            idle_timeout_seconds=assistant_config.assistant_default_idle_seconds,
            history_enabled=False,
            language="en",
        )
        db.add(row)
        db.commit()
    return row


def used_seconds(db: Session, workspace_id: str) -> float:
    row = db.get(AssistantUsage, (workspace_id, month_key()))
    return float(row.seconds) if row else 0.0


def add_usage(db: Session, workspace_id: str, seconds: float) -> None:
    if seconds <= 0:
        return
    row = db.get(AssistantUsage, (workspace_id, month_key()))
    if row is None:
        db.add(AssistantUsage(workspace_id=workspace_id, month=month_key(), seconds=seconds))
    else:
        row.seconds = float(row.seconds) + seconds
    db.commit()


def settings_out(db: Session, workspace_id: str, can_edit: bool) -> dict:
    row = get_settings_row(db, workspace_id)
    used = used_seconds(db, workspace_id)
    cap = row.monthly_minute_cap * 60
    return {
        "available": bool(assistant_config.deepgram_api_key) if (row.provider or "deepgram") == "deepgram" else True,
        "enabled": row.enabled,
        "monthlyMinuteCap": row.monthly_minute_cap,
        "usedSeconds": round(used),
        "remainingSeconds": max(0, round(cap - used)),
        "capReached": used >= cap,
        "idleTimeoutSeconds": row.idle_timeout_seconds,
        "historyEnabled": row.history_enabled,
        "language": row.language,
        "provider": row.provider or "deepgram",
        "voice": assistant_config.assistant_voice,
        "model": assistant_config.assistant_llm_model,
        "month": month_key(),
        "canEdit": can_edit,
    }


# --- tickets: the browser never holds a Deepgram credential; it holds one of these for 30 seconds ------------
@dataclass
class Ticket:
    user_id: str
    workspace_id: str
    mode: str
    language: str
    page: dict
    expires: float
    session_id: str = field(default_factory=lambda: secrets.token_hex(8))


_tickets: dict[str, Ticket] = {}
_active: dict[str, int] = {}  # workspace id -> running sessions
_lock = threading.Lock()


def issue_ticket(user_id: str, workspace_id: str, mode: str, language: str, page: dict) -> str:
    token = secrets.token_urlsafe(32)
    now = time.monotonic()
    with _lock:
        for key in [k for k, t in _tickets.items() if t.expires < now]:
            del _tickets[key]
        _tickets[token] = Ticket(user_id, workspace_id, mode, language, page, now + assistant_config.assistant_ticket_ttl_seconds)
    return token


def redeem_ticket(token: str) -> Ticket | None:
    """Single use: a ticket works once, then is gone."""
    with _lock:
        ticket = _tickets.pop(token, None)
    if ticket is None or ticket.expires < time.monotonic():
        return None
    return ticket


def session_started(workspace_id: str) -> bool:
    with _lock:
        if _active.get(workspace_id, 0) >= assistant_config.assistant_max_sessions_per_workspace:
            return False
        _active[workspace_id] = _active.get(workspace_id, 0) + 1
        return True


def session_ended(workspace_id: str) -> None:
    with _lock:
        _active[workspace_id] = max(0, _active.get(workspace_id, 0) - 1)
