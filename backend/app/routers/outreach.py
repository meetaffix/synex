"""Outreach controls: the global kill switch and campaign dry runs."""
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
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


# ---- safety information: the hard ceilings and the audit log ----------------------------------------------------------------

RESULT_REASONS = {
    "sent": "Done.", "visited": "Done.", "followed": "Done.", "liked": "Done.", "withdrawn": "Done.", "already_connected": "Already connected, so nothing was needed.",
    "already_pending": "An invitation was already waiting.", "already_following": "Already following.", "already_liked": "Already liked.",
    "weekly_limit_reached": "LinkedIn's weekly invitation limit was reached, so the action waits a day.", "not_connected": "Not connected yet, so the message waits.",
    "profile_unavailable": "The profile could not be opened, so the person was skipped.", "needs_review": "LinkedIn showed a warning after the click, so everything stopped for review.",
    "logged_out": "LinkedIn signed the account out.", "checkpoint": "LinkedIn asked for a security check.", "restricted": "LinkedIn restricted the account.",
    "no_credits": "No InMail credits were left.", "not_free": "The profile does not offer a free message.", "no_posts": "The person has no recent post to like.",
    "not_pending": "The invitation was not pending any more.",
}


# The same result word means different things for different actions: "not connected" on a message is a failure, on a connection check it is an answer.
TYPE_REASONS = {
    ("send_message", "not_connected"): "LinkedIn did not offer a Message button for this person, so nothing was sent.",
    ("send_voice_note", "not_connected"): "LinkedIn did not offer a Message button for this person, so nothing was sent.",
    ("check_connection", "not_connected"): "Not connected yet.",
    ("check_connection", "pending"): "The connection request is still waiting for an answer.",
    ("check_connection", "connected"): "Connected.",
}
RETRY_WORDS = "LinkedIn did not answer in time. Synex tries again later; nothing was sent."


def reason_for(step: str | None, result: str | None) -> str:
    """The result of an action in plain words. Never a raw error name."""
    result = result or ""
    if (step, result) in TYPE_REASONS:
        return TYPE_REASONS[(step, result)]
    if result.startswith("retry_"):
        return RETRY_WORDS if step not in ("sync_inbox", "sync_connections", "collect_leads") else "LinkedIn did not answer in time. Synex tries again later."
    if result.startswith("failed_"):
        return "Failed, and nothing was sent." if step not in ("sync_inbox", "sync_connections", "collect_leads") else "Could not read LinkedIn; it will be tried again."
    if result.startswith("needs_review_"):
        return RESULT_REASONS["needs_review"]
    if result.startswith("skipped_"):
        return "Skipped: " + result[len("skipped_"):].replace("_", " ") + "."
    if result.startswith("synced_"):
        return f"Read {result[len('synced_'):]} conversations."
    return RESULT_REASONS.get(result, result.replace("_", " ").capitalize())


SEND_STEPS = ("send_invite", "send_message", "send_inmail", "send_voice_note", "withdraw_invite", "follow_profile", "like_post", "engage_post", "visit_profile")


def describe(step: str | None, result: str | None, person: str | None, campaign: str | None, text: str | None) -> str:
    """One line for the audit log: what happened, to whom, and for a message the words that were going to be sent."""
    parts = [reason_for(step, result)]
    if person:
        parts.append(f"To {person}" + (f", campaign {campaign}." if campaign else "."))
    if text and step in ("send_message", "send_inmail", "send_invite"):
        parts.append("Text: " + (text if len(text) <= 300 else text[:300] + "..."))
    return " ".join(parts)


@router.get("/outreach/ceilings")
def ceilings(user: models.User = Depends(get_data_user)):
    """The hard limits no setting can raise, and the test profile."""
    from .. import account_policy
    from ..config import DAILY_ACTION_CEILING, DAILY_TYPE_CEILINGS, WEEKLY_INVITE_CEILING
    return {"daily": [{"action": a, "label": account_policy.LABELS.get(a, a.replace("_", " ").capitalize()), "ceiling": c} for a, c in DAILY_TYPE_CEILINGS.items()],
            "dailyTotal": DAILY_ACTION_CEILING, "weeklyInvites": WEEKLY_INVITE_CEILING, "newAccountDailyLimit": 0,
            "testProfile": {a: v["dailyLimit"] for a, v in account_policy.test_profile_actions().items()}}


@router.get("/outreach/audit")
def audit(limit: int = 50, offset: int = 0, account_id: str | None = Query(None, alias="accountId"), db: Session = Depends(get_db), user: models.User = Depends(get_data_user)):
    """Every action Synex took on LinkedIn for this workspace, newest first, with the account, the person, the campaign and why it ended as it did."""
    limit, offset = max(1, min(limit, 200)), max(0, offset)
    query = db.query(models.AgentActivity).filter(models.AgentActivity.user_id == user.id, models.AgentActivity.scope == "task")
    if account_id:
        query = query.filter(models.AgentActivity.account_id == account_id)
    total = query.count()
    rows = query.order_by(models.AgentActivity.created_at.desc()).offset(offset).limit(limit).all()
    task_ids = [r.task_id for r in rows if r.task_id]
    tasks = {t.id: t for t in db.query(models.AgentTask).filter(models.AgentTask.id.in_(task_ids)).all()} if task_ids else {}
    lead_ids = {(t.payload or {}).get("leadId") for t in tasks.values()} - {None}
    leads = {l.id: l for l in db.query(models.Lead).filter(models.Lead.id.in_(lead_ids), models.Lead.user_id == user.id).all()} if lead_ids else {}
    campaigns = {c.id: c.name for c in db.query(models.Campaign).filter(models.Campaign.id.in_({r.campaign_id for r in rows if r.campaign_id}), models.Campaign.user_id == user.id).all()} if rows else {}
    accounts = {a.id: a.name for a in db.query(models.LinkedInAccount).filter(models.LinkedInAccount.user_id == user.id).all()}
    items = []
    for r in rows:
        lead = leads.get((tasks[r.task_id].payload or {}).get("leadId")) if r.task_id in tasks else None
        items.append({"id": r.id, "at": r.created_at.isoformat(), "account": accounts.get(r.account_id, "A removed account"), "action": r.step, "result": r.result, "status": r.status,
                      "reason": reason_for(r.step, r.result) or None, "person": f"{lead.first_name} {lead.last_name}".strip() if lead else None,
                      "campaign": campaigns.get(r.campaign_id)})
    return {"items": items, "total": total, "limit": limit, "offset": offset,
            "note": "Synex keeps the most recent actions of each account; older rows are removed to keep the log small."}
