"""Plan limits, read from the database. The server enforces them; the browser only shows them.

The numbers seeded here are placeholders until pricing is decided. A row that already exists is never overwritten, so an operator can change a limit in the database.
"""
from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models

SEED = [("free", "Free", 0, 60), ("pro", "Pro", 1, 600), ("scale", "Scale", 2, 3000)]
DEFAULT = "free"


def ensure_plans(db: Session) -> None:
    """Add any missing plan row. Safe to run again and while another process boots (a lost race is ignored)."""
    for plan_id, name, position, minutes in SEED:
        if db.get(models.Plan, plan_id) is None:
            db.add(models.Plan(id=plan_id, name=name, position=position, assistant_minutes=minutes))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()


def plan_of(db: Session, workspace_owner: models.User) -> models.Plan:
    """The workspace owner's plan row; an unknown plan name falls back to the free plan."""
    ensure_plans(db)
    return db.get(models.Plan, (workspace_owner.plan or DEFAULT).lower()) or db.get(models.Plan, DEFAULT)


def assistant_minute_limit(db: Session, workspace_id: str) -> int:
    owner = db.get(models.User, workspace_id)
    return plan_of(db, owner).assistant_minutes if owner else db.get(models.Plan, DEFAULT).assistant_minutes
