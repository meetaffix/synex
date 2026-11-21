"""The workspace's plan: what it includes, what has been used, and whether it can be changed. Everything here is read from the database."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, plans
from ..assistant import service
from ..database import get_db
from ..deps import get_current_user, resolve_workspace

router = APIRouter(tags=["plan"])


@router.get("/plan")
def read_plan(db: Session = Depends(get_db), actor: models.User = Depends(get_current_user)):
    owner, role = resolve_workspace(db, actor)
    current = plans.plan_of(db, owner)
    used = round(service.used_seconds(db, owner.id) / 60, 1)
    limits = plans.limits_of(db, owner)
    return {
        "plan": current.id, "name": current.name,
        "limits": limits,
        "seats": {"used": plans.seats_used(db, owner.id), "limit": limits["seats"]},
        "assistantMinutes": {"used": used, "limit": limits["assistantMinutes"], "month": service.month_key()},
        "plans": [{"id": p.id, "name": p.name, "assistantMinutes": p.assistant_minutes, "seats": p.seats, "dailyInvites": p.daily_invites,
                   "dailyMessages": p.daily_messages, "dailyVisits": p.daily_visits, "current": p.id == current.id}
                  for p in db.query(models.Plan).order_by(models.Plan.position).all()],
        "canManage": role == "admin",
        # Billing is not built, so a plan cannot be bought or changed from the app yet. Said plainly instead of a button that does nothing.
        "upgradeAvailable": False,
        "upgradeNote": "Changing plan is not available yet: billing is not built. Your current limits stay as shown.",
    }
