"""Plan limits, read from the database. The server enforces them; the browser only shows them.

A plan sets how many LinkedIn sender accounts a workspace may hold and how much each account may send in a day. The daily
numbers are always held under the hard safety ceilings in config.py: no plan, override or setting can raise those.
Billing is not built, so a plan is assigned (users.plan), not bought. Enterprise and special deals use users.plan_overrides.

The numbers seeded here are placeholders until pricing is decided. A row that already exists keeps its values, so an operator can change a limit in the database.
"""
from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models
from .config import DAILY_TYPE_CEILINGS

# id, name, position, assistant minutes, seats, daily invites, daily messages, daily profile visits (each per sender account)
SEED = [
    ("free", "Demo", 0, 60, 1, 10, 20, 20),
    ("pro", "Pro", 1, 600, 15, 30, 80, 60),
    ("scale", "Scale", 2, 3000, 30, 40, 100, 80),
    ("enterprise", "Enterprise", 3, 10000, 500, 40, 100, 80),
]
DEFAULT = "free"
# plan field -> (override key, action type whose hard ceiling bounds it)
DAILY = {"daily_invites": ("dailyInvites", "send_invite"), "daily_messages": ("dailyMessages", "send_message"), "daily_visits": ("dailyVisits", "visit_profile")}
TYPE_FIELD = {"send_invite": "daily_invites", "send_message": "daily_messages", "visit_profile": "daily_visits"}


def ensure_plans(db: Session) -> None:
    """Add any missing plan row and fill the limit columns of rows made before they existed. Safe to run again and while another process boots."""
    for plan_id, name, position, minutes, seats, invites, messages, visits in SEED:
        row = db.get(models.Plan, plan_id)
        if row is None:
            db.add(models.Plan(id=plan_id, name=name, position=position, assistant_minutes=minutes, seats=seats,
                               daily_invites=invites, daily_messages=messages, daily_visits=visits))
        else:
            for field, value in (("seats", seats), ("daily_invites", invites), ("daily_messages", messages), ("daily_visits", visits)):
                if getattr(row, field) is None:
                    setattr(row, field, value)
            if plan_id == "free" and row.name == "Free":
                row.name = name  # the free plan is the demo plan
        try:
            db.commit()
        except IntegrityError:
            db.rollback()


def plan_of(db: Session, workspace_owner: models.User) -> models.Plan:
    """The workspace owner's plan row; an unknown plan name falls back to the free plan."""
    ensure_plans(db)
    return db.get(models.Plan, (workspace_owner.plan or DEFAULT).lower()) or db.get(models.Plan, DEFAULT)


def limits_of(db: Session, workspace_owner: models.User) -> dict:
    """What this workspace may do: the plan's numbers with the owner's overrides on top, daily sending held under the hard ceilings."""
    plan = plan_of(db, workspace_owner)
    over = workspace_owner.plan_overrides if isinstance(workspace_owner.plan_overrides, dict) else {}

    def pick(key: str, base: int | None) -> int | None:
        value = over.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else base

    out = {"seats": pick("seats", plan.seats), "assistantMinutes": pick("assistantMinutes", plan.assistant_minutes)}
    for field, (key, ttype) in DAILY.items():
        value = pick(key, getattr(plan, field))
        out[key] = DAILY_TYPE_CEILINGS[ttype] if value is None else min(value, DAILY_TYPE_CEILINGS[ttype])
    return out


def assistant_minute_limit(db: Session, workspace_id: str) -> int:
    owner = db.get(models.User, workspace_id)
    return limits_of(db, owner)["assistantMinutes"] if owner else db.get(models.Plan, DEFAULT).assistant_minutes


def seats_used(db: Session, workspace_id: str) -> int:
    """Sender accounts that hold a seat: every account not deleted or deactivated, including one waiting for its owner to sign in."""
    return db.query(models.LinkedInAccount).filter(models.LinkedInAccount.user_id == workspace_id,
                                                   models.LinkedInAccount.status.notin_(["deleted", "deactivated"])).count()


def seat_refusal(db: Session, workspace_id: str) -> str | None:
    """Why another sender account cannot be added, or None when there is a free seat."""
    owner = db.get(models.User, workspace_id)
    if owner is None:
        return None
    seats = limits_of(db, owner)["seats"]
    if seats is not None and seats_used(db, workspace_id) >= seats:
        name = plan_of(db, owner).name
        return f"Your {name} plan includes {seats} LinkedIn account{'s' if seats != 1 else ''}, and all are in use. Upgrade to add another."
    return None


def daily_cap(db: Session, workspace_id: str, ttype: str) -> int | None:
    """The plan's daily cap for this action on one account, or None when the plan does not cap the action."""
    field = TYPE_FIELD.get(ttype)
    owner = db.get(models.User, workspace_id) if field else None
    if owner is None:
        return None
    return limits_of(db, owner)[DAILY[field][0]]
