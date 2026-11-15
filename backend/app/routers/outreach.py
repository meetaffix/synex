"""Outreach controls: the global kill switch and campaign dry runs."""
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.orm import Session

from .. import engine, models, planner
from ..config import settings
from ..database import get_db
from ..deps import get_current_user, get_data_user
from ..publishing_models import WorkerHeartbeat

router = APIRouter(tags=["outreach"])
HEARTBEAT_FRESH = timedelta(minutes=2)


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class KillSwitchIn(CamelModel):
    enabled: bool


class OutreachStatusOut(CamelModel):
    kill_switch: bool
    forced_by_setting: bool
    workers_active: int


class PlannedActionOut(CamelModel):
    lead_id: str
    lead_name: str
    account_id: str | None
    account_name: str | None
    step_id: str | None
    step_order: int | None
    step_type: str | None
    task_type: Literal["send_invite", "send_message", "visit_profile", "follow_profile", "check_connection"] | None
    message: str
    ai_personalized: bool
    earliest_at: datetime | None
    skip_reason: str | None


class DryRunOut(CamelModel):
    campaign_id: str
    generated_at: datetime
    actions: list[PlannedActionOut]


def platform_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if (user.role or "").strip().lower() != "admin":
        raise HTTPException(403, "Only a platform administrator can use this control.")
    return user


def _status(db: Session) -> OutreachStatusOut:
    fresh = datetime.now(timezone.utc) - HEARTBEAT_FRESH
    beats = [b for b in db.query(WorkerHeartbeat).filter(WorkerHeartbeat.id.like("outreach-%")).all()
             if engine._aware(b.checked_at) >= fresh]
    return OutreachStatusOut(kill_switch=engine.kill_switch_active(db), forced_by_setting=settings.outreach_kill_switch,
                             workers_active=len(beats))


@router.get("/outreach/status", response_model=OutreachStatusOut)
def outreach_status(db: Session = Depends(get_db), _admin: models.User = Depends(platform_admin)):
    return _status(db)


@router.post("/outreach/kill-switch", response_model=OutreachStatusOut)
def set_kill_switch(body: KillSwitchIn, db: Session = Depends(get_db), admin: models.User = Depends(platform_admin)):
    """Stops (or resumes) all task execution for every workspace. Workers check it before every action."""
    control = db.get(models.OutreachControl, "global") or models.OutreachControl(id="global")
    control.kill_switch, control.updated_by = body.enabled, admin.id
    db.add(control)
    db.commit()
    return _status(db)


@router.post("/campaigns/{campaign_id}/dry-run", response_model=DryRunOut)
def dry_run(campaign_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_data_user)):
    """The next planned actions (up to 50) for this campaign. Sends nothing and changes nothing."""
    campaign = db.get(models.Campaign, campaign_id)
    if campaign is None or campaign.user_id != user.id:
        raise HTTPException(404, "Campaign not found")
    now = datetime.now(timezone.utc)
    actions = [PlannedActionOut(**{k: getattr(a, k) for k in PlannedActionOut.model_fields}) for a in planner.plan_campaign(db, campaign, now)]
    return DryRunOut(campaign_id=campaign.id, generated_at=now, actions=actions)
