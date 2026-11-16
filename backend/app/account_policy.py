"""Sender budgets shared by settings, planning, manual replies and execution.

Budget variation is deterministic within an account-local day, never exceeds the
owner's target or the hard ceiling, and never turns a stopped action back on.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Literal

from pydantic import Field, model_validator
from sqlalchemy import func

from .config import DAILY_TYPE_CEILINGS
from .linkedin_session.schemas_base import CamelModel


PRESETS = {"conservative": (1, 7), "balanced": (2, 3), "aggressive": (3, 1)}
LABELS = {
    "visit_profile": "Profile views", "send_invite": "Connection requests",
    "send_message": "Messages", "follow_profile": "Profile follows",
    "check_connection": "Connection checks", "sync_inbox": "Inbox reads",
    "sync_connections": "Connection list reads",
    "collect_leads": "Lead collection pages", "withdraw_invite": "Invitation withdrawals",
    "like_post": "Post likes", "send_inmail": "InMails", "send_voice_note": "Voice notes",
}


class ActionPolicy(CamelModel):
    daily_limit: int = Field(ge=0)
    increase_by: int = Field(default=0, ge=0, le=10)
    stop_at: int = Field(ge=0)
    interval_days: int = Field(default=7, ge=1, le=365)
    dynamic_interval: bool = False

    @model_validator(mode="after")
    def order(self):
        if self.stop_at < self.daily_limit:
            raise ValueError("Stop at must be at least the daily limit")
        return self


class SenderPolicy(CamelModel):
    preset: Literal["off", "conservative", "balanced", "aggressive", "custom"] = "off"
    range: int = Field(default=1, ge=1, le=10)
    actions: dict[str, ActionPolicy] = Field(default_factory=dict)
    auto_withdraw: bool = False
    stale_invite_days: int = Field(default=30, ge=7, le=365)
    inbox_history_days: int = Field(default=90, ge=1, le=3650)

    @model_validator(mode="after")
    def ceilings(self):
        for action, policy in self.actions.items():
            if action not in DAILY_TYPE_CEILINGS:
                raise ValueError(f"Unknown action: {action}")
            if policy.stop_at > DAILY_TYPE_CEILINGS[action]:
                raise ValueError(f"{action}: maximum {DAILY_TYPE_CEILINGS[action]}")
        return self


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def policy_for(account) -> SenderPolicy:
    return SenderPolicy.model_validate((account.management_config or {}).get("policy", {}))


def bounds(account, action: str, now: datetime) -> tuple[int, int, int]:
    """(low, high, today's budget), bounded even for legacy or corrupted values."""
    from .engine import account_tz, _local
    ceiling = DAILY_TYPE_CEILINGS.get(action, 0)
    policy = policy_for(account)
    action_policy = policy.actions.get(action)
    if action_policy is None:
        return ceiling, ceiling, ceiling
    base = min(action_policy.daily_limit, ceiling)
    if base == 0:
        return 0, 0, 0
    started = (account.management_config or {}).get("policyStartedAt")
    start = _aware(datetime.fromisoformat(started)) if started else _aware(now)
    days = max(0, (_aware(now) - start).days)
    increment, interval = action_policy.increase_by, action_policy.interval_days
    if policy.preset in PRESETS:
        increment, interval = PRESETS[policy.preset]
    if policy.preset == "off":
        increment = 0
    # Alternates 3/2-day intervals for Balanced and custom dynamic intervals.
    periods = days * 2 // 5 if policy.preset == "balanced" or action_policy.dynamic_interval else days // interval
    target = min(ceiling, action_policy.stop_at, base + increment * periods)
    low = max(0, target - policy.range)
    high = min(ceiling, action_policy.stop_at, target + policy.range)
    # A fixed daily budget avoids accidentally resampling into a higher quota on each request.
    day = _local(now, account_tz(account)).date().isoformat()
    seed = int.from_bytes(sha256(f"{account.id}:{action}:{day}".encode()).digest()[:8], "big")
    return low, high, low + seed % (high - low + 1)


def rolling_usage(db, account_id: str, now: datetime, action: str | None = None, *, exclude_task: str | None = None) -> int:
    from .models import AgentTask
    query = db.query(func.count(AgentTask.id)).filter(
        AgentTask.account_id == account_id, AgentTask.status.in_(("pending", "running", "done", "needs_review")),
        func.coalesce(AgentTask.committed_at, AgentTask.created_at) >= now - timedelta(hours=24))
    if action:
        query = query.filter(AgentTask.type == action)
    if exclude_task:
        query = query.filter(AgentTask.id != exclude_task)
    return query.scalar() or 0


def action_room(db, account, action: str, now: datetime, *, exclude_task: str | None = None) -> int:
    return bounds(account, action, now)[2] - rolling_usage(db, account.id, now, action, exclude_task=exclude_task)


def usage_rows(db, account, now: datetime) -> list[dict]:
    rows = []
    for action, ceiling in DAILY_TYPE_CEILINGS.items():
        low, high, budget = bounds(account, action, now)
        rows.append({"action": action, "label": LABELS.get(action, action.replace("_", " ").capitalize()),
                     "used": rolling_usage(db, account.id, now, action), "low": low, "high": high,
                     "budget": budget, "ceiling": ceiling})
    return rows
