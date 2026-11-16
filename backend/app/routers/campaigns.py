from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..errors import sanitize_errors
from ..database import get_db
from ..deps import get_data_user, get_manager_user
from ..serializers import campaign_out
from ..schemas import CampaignIn, CampaignUpdateIn, RunActionIn
from .. import campaign_settings, models, engine

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


def _parse(model, body: dict):
    try:
        return model.model_validate(body)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=sanitize_errors(e.errors()))


def _default_steps() -> list[dict]:
    """Starter sequence structure. Messages are intentionally empty — the user
    writes their own copy in the sequence builder."""
    return [
        {"type": "connection_request", "order": 0, "message": ""},
        {"type": "wait", "order": 1, "delay_hours": 48},
        {"type": "message", "order": 2, "message": ""},
        {"type": "wait", "order": 3, "delay_hours": 72},
        {"type": "follow_up", "order": 4, "message": ""},
        {"type": "end", "order": 5},
    ]


def _owned(db: Session, user: models.User, campaign_id: str) -> models.Campaign:
    c = db.get(models.Campaign, campaign_id)
    if not c or c.user_id != user.id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return c


def _validate_launch(db: Session, campaign: models.Campaign) -> None:
    """Refuse to launch into a state where nothing can execute. Every missing item is
    reported at once, each with its own error type, as a 422."""
    problems: list[dict] = []

    def missing(kind: str, field: str, message: str) -> None:
        problems.append({"loc": ["body", field], "msg": message, "type": f"launch.{kind}"})

    now = datetime.now(timezone.utc)
    if not any(engine.account_is_live(a, now) for a in engine.campaign_accounts(db, campaign)):
        missing("no_connected_account", "accountId",
                "Select a connected sender account for this campaign. Connect one under Sender accounts if you have none.")
    if not (campaign.lead_list_id and campaign.lead_list and campaign.lead_list.leads):
        missing("empty_lead_list", "leadListId", "Add at least one lead to the campaign's list before launching.")
    if not campaign.steps:
        missing("no_steps", "steps", "Add at least one step to the sequence before launching.")
    else:
        actionable = [s for s in campaign.steps if s.type not in ("wait", "end")]
        if not actionable:
            missing("no_actionable_step", "steps", "The sequence has no action. Add a connection request or a message.")
        if any(s.type in ("message", "follow_up") and not (s.message or "").strip() for s in actionable):
            missing("empty_message", "steps", "One or more message steps are empty. Write the message copy before launching.")
    days, start, end = campaign.working_days or [], campaign.start_hour, campaign.end_hour
    if campaign.week_schedule:
        hours_ok = engine._zone(campaign.timezone) is not None and any(e.get("on") for e in campaign.week_schedule.values())
    else:
        hours_ok = None
    hours_ok = hours_ok if hours_ok is not None else (
        bool(days) and all(isinstance(d, int) and 0 <= d <= 6 for d in days)
        and isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= 24
        and engine._zone(campaign.timezone) is not None
    )
    if not hours_ok:
        missing("invalid_working_hours", "startHour",
                "Set valid working hours: at least one working day, a start hour before the end hour, and a known timezone.")
    if problems:
        raise HTTPException(status_code=422, detail=problems)


def _apply_steps(campaign: models.Campaign, steps) -> None:
    """Replace the sequence, keeping the id of every step that is still present so runs
    in flight keep their position (they are stored by step id)."""
    existing = {s.id: s for s in campaign.steps}
    updated: list[models.CampaignStep] = []
    for i, raw in enumerate(steps):
        data = raw if isinstance(raw, dict) else raw.model_dump()
        step = existing.get(data.get("id") or "") or models.CampaignStep(type=data["type"])
        step.type = data["type"]
        step.order = data.get("order", i)
        step.message = data.get("message")
        step.delay_hours = data.get("delay_hours")
        step.parent_step_id = data.get("parent_step_id")
        step.branch_condition = data.get("branch_condition")
        step.ai_config = data.get("ai_config")
        updated.append(step)
    campaign.steps[:] = updated


@router.get("")
def read_campaigns(
    id: str | None = Query(None),
    monitor: bool = Query(False),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_data_user),
):
    """Reads for campaigns:

    * no params — list all campaigns
    * ``?id=X`` — a single campaign
    * ``?id=X&monitor=1`` — that campaign's live execution monitor
    """
    if id:
        if monitor:
            return _monitor(id, db, user)
        return campaign_out(_owned(db, user, id))
    campaigns = (
        db.query(models.Campaign)
        .filter(models.Campaign.user_id == user.id)
        .order_by(models.Campaign.created_at.desc())
        .all()
    )
    return [campaign_out(c) for c in campaigns]


def _create(payload: CampaignIn, db: Session, user: models.User):
    campaign = models.Campaign(
        user_id=user.id,
        name=payload.name,
        description=payload.description,
        status="draft",
        account_id=payload.account_id or None,
        account_ids=payload.account_ids or [],
        lead_list_id=payload.lead_list_id or None,
        daily_connection_limit=20 if payload.daily_connection_limit is None else payload.daily_connection_limit,
        daily_message_limit=40 if payload.daily_message_limit is None else payload.daily_message_limit,
        timezone=payload.timezone or "America/New_York",
        start_hour=payload.start_hour if payload.start_hour is not None else 9,
        end_hour=payload.end_hour if payload.end_hour is not None else 17,
        working_days=payload.working_days or [1, 2, 3, 4, 5],
        random_delay=payload.random_delay if payload.random_delay is not None else True,
        stop_when_replied=payload.stop_when_replied if payload.stop_when_replied is not None else True,
        stop_when_accepted=payload.stop_when_accepted if payload.stop_when_accepted is not None else False,
        ai_personalization=payload.ai_personalization if payload.ai_personalization is not None else False,
        pause_on_failure=payload.pause_on_failure if payload.pause_on_failure is not None else False,
        audience_source=payload.audience_source,
        week_schedule=payload.week_schedule, exclusions=payload.exclusions, allocation=payload.allocation,
        ai_context=payload.ai_context, sequence_mode=payload.sequence_mode or "classic", graph=payload.graph,
    )
    db.add(campaign)
    db.flush()
    _apply_steps(campaign, payload.steps if payload.steps else _default_steps())
    db.commit()
    db.refresh(campaign)
    return campaign_out(campaign)


def _update(campaign_id: str, payload: CampaignUpdateIn, db: Session, user: models.User):
    campaign = _owned(db, user, campaign_id)
    data = payload.model_dump(exclude_unset=True)
    for key in (
        "name", "description", "status", "account_id", "account_ids", "lead_list_id",
        "daily_connection_limit", "daily_message_limit",
        "timezone", "start_hour", "end_hour", "working_days",
        "random_delay", "stop_when_replied", "stop_when_accepted",
        "ai_personalization", "pause_on_failure", "audience_source",
        "week_schedule", "exclusions", "allocation", "ai_context", "sequence_mode", "graph",
    ):
        if key in data and data[key] is not None:
            setattr(campaign, key, data[key])

    if payload.steps is not None:
        _apply_steps(campaign, payload.steps)

    # Going live: validate, stamp launch time, and enroll prospects in the engine.
    if data.get("status") == "active":
        _validate_launch(db, campaign)
        if campaign.launched_at is None:
            campaign.launched_at = datetime.now(timezone.utc)
        engine.launch_campaign(db, campaign)

    db.commit()
    db.refresh(campaign)
    return campaign_out(campaign)


# ---------------------------------------------------------------------------
# Live monitoring & failed-action recovery
# ---------------------------------------------------------------------------
def _lead_name(lead: models.Lead | None) -> str:
    if lead is None:
        return "Unknown"
    return f"{lead.first_name} {lead.last_name}".strip() or "Unknown"


def _task_out(t: models.AgentTask) -> dict:
    run = t.sequence_run
    lead = run.lead if run else None
    return {
        "id": t.id,
        "runId": t.sequence_run_id,
        "type": t.type,
        "status": t.status,
        "attempts": t.attempts or 0,
        "leadId": lead.id if lead else None,
        "leadName": _lead_name(lead),
        "error": (t.result or {}).get("detail") if t.result else None,
        "createdAt": t.created_at.isoformat() if t.created_at else None,
        "updatedAt": t.updated_at.isoformat() if t.updated_at else None,
    }


def _monitor(campaign_id: str, db: Session, user: models.User):
    """Real-time execution view: run pipeline, in-flight actions, the last
    executed action, the next scheduled one, and failures with errors."""
    campaign = _owned(db, user, campaign_id)
    now = datetime.now(timezone.utc)

    runs = (
        db.query(models.SequenceRun)
        .filter(models.SequenceRun.campaign_id == campaign.id)
        .all()
    )
    run_counts: dict[str, int] = {}
    for r in runs:
        run_counts[r.status] = run_counts.get(r.status, 0) + 1
    failed_runs = [r for r in runs if r.status == "stopped" and r.stop_reason == "send_failed"]

    run_ids = [r.id for r in runs]
    tasks = (
        db.query(models.AgentTask)
        .filter(models.AgentTask.sequence_run_id.in_(run_ids))
        .order_by(models.AgentTask.updated_at.desc())
        .all()
        if run_ids
        else []
    )
    in_flight = [t for t in tasks if t.status in ("pending", "running")]
    executed = [t for t in tasks if t.status in ("done", "failed", "needs_review")]
    failed_tasks = [t for t in tasks if t.status in ("failed", "needs_review")]

    pending_runs = [
        r for r in runs
        if r.status in ("running", "waiting_connection") and r.next_action_at is not None
    ]
    next_run = min(pending_runs, key=lambda r: r.next_action_at, default=None)

    accounts = engine.campaign_accounts(db, campaign)
    steps = engine.sorted_steps(campaign)
    return {
        "campaignId": campaign.id,
        "status": campaign.status,
        # surfaced as "failed" when nothing is progressing and failures exist
        "health": (
            "failed"
            if failed_runs and not in_flight and not pending_runs
            else "attention" if failed_runs or failed_tasks else "ok"
        ),
        "runCounts": run_counts,
        "currentActions": [_task_out(t) for t in in_flight[:20]],
        "lastExecuted": _task_out(executed[0]) if executed else None,
        "nextScheduled": (
            {
                "runId": next_run.id,
                "leadId": next_run.lead_id,
                "leadName": _lead_name(next_run.lead),
                "stepOrder": engine.step_order_of(steps, next_run),
                "at": next_run.next_action_at.isoformat(),
            }
            if next_run
            else None
        ),
        "failures": [_task_out(t) for t in failed_tasks[:50]],
        "failedRuns": [
            {
                "runId": r.id,
                "leadId": r.lead_id,
                "leadName": _lead_name(r.lead),
                "stepOrder": engine.step_order_of(steps, r),
                "stoppedAt": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in failed_runs
        ],
        "accounts": [
            {
                "id": a.id,
                "name": a.name,
                "live": engine.account_is_live(a, now),
                "dailyActionsUsed": a.daily_actions_used or 0,
                "dailyActionLimit": engine.effective_daily_limit(a, now),
            }
            for a in accounts
        ],
    }


def _owned_run(db: Session, user: models.User, campaign_id: str, run_id: str) -> models.SequenceRun:
    campaign = _owned(db, user, campaign_id)
    run = db.get(models.SequenceRun, run_id)
    if not run or run.campaign_id != campaign.id:
        raise HTTPException(status_code=404, detail="Sequence run not found")
    return run


def _run_action(campaign_id: str, run_id: str, payload: RunActionIn, db: Session, user: models.User):
    """Unstick a failed run. ``action: "retry"`` resumes it at the same step;
    ``action: "skip"`` advances past the failing step. Either way old failed
    attempts are archived so the failure counter restarts."""
    if payload.action not in ("retry", "skip"):
        raise HTTPException(status_code=400, detail="action must be 'retry' or 'skip'")
    run = _owned_run(db, user, campaign_id, run_id)
    now = datetime.now(timezone.utc)
    # Archive previous failed attempts so the failure counter restarts, and free their
    # idempotency keys so the step can be queued again.
    for old in db.query(models.AgentTask).filter(
        models.AgentTask.sequence_run_id == run.id,
        models.AgentTask.status.in_(["failed", "needs_review"]),
    ).all():
        old.status = "abandoned"
        old.idempotency_key = f"{old.idempotency_key}:abandoned:{old.id[:8]}"
    run.status = "running"
    run.stop_reason = None
    run.completed_at = None
    run.next_action_at = now
    if payload.action == "skip":
        steps = engine.sorted_steps(run.campaign)
        step = engine.current_step(steps, run)
        if step is not None:
            engine.move_past(steps, run, step, now)
        note = "Failed step skipped manually"
    else:
        note = "Failed action retried manually"
    if run.lead:
        engine.record_event(db, run.lead, "note", note, campaign=run.campaign)
    db.commit()
    return {"ok": True, "runId": run.id, "status": run.status,
            "stepOrder": engine.step_order_of(engine.sorted_steps(run.campaign), run)}


def _delete(campaign_id: str, db: Session, user: models.User):
    campaign = _owned(db, user, campaign_id)
    db.delete(campaign)
    db.commit()
    return {"ok": True}


@router.post("")
def write_campaigns(
    body: dict,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_manager_user),
):
    """Single write gateway for campaigns. ``action`` selects the operation:

    * ``create`` — new campaign (CampaignIn fields)
    * ``update`` — ``id`` + changed CampaignUpdateIn fields (status=active launches it)
    * ``delete`` — ``id``
    * ``run``    — act on a sequence run: ``id``, ``runId``, ``runAction`` ("retry"|"skip")
    """
    action = body.get("action")
    if action == "create":
        return _create(_parse(CampaignIn, body), db, user)
    if action == "update":
        if not body.get("id"):
            raise HTTPException(status_code=400, detail="id is required to update a campaign")
        return _update(body["id"], _parse(CampaignUpdateIn, body), db, user)
    if action == "delete":
        if not body.get("id"):
            raise HTTPException(status_code=400, detail="id is required to delete a campaign")
        return _delete(body["id"], db, user)
    if action == "run":
        if not (body.get("id") and body.get("runId")):
            raise HTTPException(status_code=400, detail="id and runId are required for a run action")
        return _run_action(
            body["id"], body["runId"], _parse(RunActionIn, {"action": body.get("runAction")}), db, user
        )
    raise HTTPException(status_code=400, detail=f"Unknown campaign action: {action!r}")
