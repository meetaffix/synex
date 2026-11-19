import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..errors import sanitize_errors
from ..database import get_db
from ..deps import get_data_user, get_manager_user
from ..serializers import campaign_out
from ..schemas import CampaignIn, CampaignUpdateIn, RunActionIn, StepIn
from .. import campaign_settings, integrations_core, models, engine

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


def launch_problems(db: Session, campaign: models.Campaign) -> list[dict]:
    """Everything that stops a launch, each with its own kind, a message that says how to fix it, and the wizard step to go to."""
    from .. import ai_prompt
    problems: list[dict] = []

    def missing(kind: str, field: str, message: str, step: str) -> None:
        problems.append({"kind": kind, "field": field, "message": message, "step": step})

    now = datetime.now(timezone.utc)
    if not any(engine.account_is_live(a, now) for a in engine.campaign_accounts(db, campaign)):
        missing("no_connected_account", "accountId",
                "Select a connected sender account for this campaign. Connect one under Sender accounts if you have none.", "senders")
    if not (campaign.lead_list_id and campaign.lead_list and campaign.lead_list.leads):
        missing("empty_lead_list", "leadListId", "Add at least one lead to the campaign's list before launching.", "leads")
    if not campaign.steps:
        missing("no_steps", "steps", "Add at least one step to the sequence before launching.", "sequence")
    else:
        from .. import step_types
        actionable = [s for s in campaign.steps if s.type not in ("wait", "end", *step_types.CONDITIONALS)]
        if not actionable:
            missing("no_actionable_step", "steps", "The sequence has no action. Add a connection request or a message.", "sequence")
        writes = [s for s in actionable if s.type in ("message", "follow_up", "inmail", "free_inmail")]
        if any(not (s.message or "").strip() and not (s.ai_config or {}).get("mode") == "ai" for s in writes):
            missing("empty_message", "steps", "One or more message steps are empty. Write the message copy before launching.", "sequence")
        for s in actionable:
            if s.type == "voice_note":
                reason = step_types.needs_setup(s.type, s.message, s.ai_config, s.config)
                if reason:
                    missing("voice_note_not_ready", "steps", f"A voice note step is not ready. {reason}", "sequence")
                    break
        ai_steps = [s for s in actionable if (s.ai_config or {}).get("mode") == "ai"]
        if ai_steps and campaign.lead_list:
            lead_ids = [l.id for l in campaign.lead_list.leads if (l.linkedin_url or "").strip()]
            drafts_by = {}
            for d in db.query(models.LeadDraft).filter_by(campaign_id=campaign.id).all():
                drafts_by[(d.step_id, d.lead_id)] = d.status
            absent = sum(1 for s in ai_steps for lid in lead_ids if (s.id, lid) not in drafts_by)
            waiting = sum(1 for s in ai_steps for lid in lead_ids if drafts_by.get((s.id, lid)) == "proposed")
            if absent:
                missing("ai_drafts_missing", "steps", f"{absent} AI message{'s' if absent != 1 else ''} not written yet. Generate them in the Review step, or switch the step to a plain message.", "review")
            if waiting:
                missing("ai_drafts_unreviewed", "steps", f"{waiting} AI message{'s are' if waiting != 1 else ' is'} waiting for your review. Approve them in the Review step before launching.", "review")
    days, start, end = campaign.working_days or [], campaign.start_hour, campaign.end_hour
    if campaign.week_schedule:
        hours_ok = engine._zone(campaign.timezone) is not None and any(e.get("on") for e in campaign.week_schedule.values())
    else:
        hours_ok = (
            bool(days) and all(isinstance(d, int) and 0 <= d <= 6 for d in days)
            and isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= 24
            and engine._zone(campaign.timezone) is not None
        )
    if not hours_ok:
        missing("invalid_working_hours", "startHour",
                "Set valid working hours: at least one working day, a start hour before the end hour, and a known timezone.", "review")
    return problems


def _validate_launch(db: Session, campaign: models.Campaign) -> None:
    """Refuse to launch into a state where nothing can execute. Every missing item is
    reported at once, each with its own error type, as a 422."""
    problems = [{"loc": ["body", p["field"]], "msg": p["message"], "type": f"launch.{p['kind']}"} for p in launch_problems(db, campaign)]
    if problems:
        raise HTTPException(status_code=422, detail=problems)


@router.get("/{campaign_id}/launch-check")
def launch_check(campaign_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_data_user)):
    """What would stop this campaign launching right now, so the builder can show it before the owner tries."""
    campaign = _owned(db, user, campaign_id)
    problems = launch_problems(db, campaign)
    return {"ready": not problems, "problems": problems}


def _apply_steps(campaign: models.Campaign, steps) -> None:
    """Replace the sequence, keeping the id of every step that is still present so runs
    in flight keep their position (they are stored by step id)."""
    existing = {s.id: s for s in campaign.steps}
    rows = [raw if isinstance(raw, dict) else raw.model_dump() for raw in steps]
    # A new step arrives with a temporary id of the browser's choosing, so a branch can name its conditional before either is saved.
    real: dict[str, str] = {}
    created: dict[str, models.CampaignStep] = {}
    for data in rows:
        key = data.get("id") or ""
        if key and key not in existing and key not in created:
            created[key] = models.CampaignStep(type=data["type"])
            created[key].id = uuid.uuid4().hex
            real[key] = created[key].id
    types = {(data.get("id") or ""): data["type"] for data in rows}
    check_tree(rows, types)
    updated: list[models.CampaignStep] = []
    for i, data in enumerate(rows):
        key = data.get("id") or ""
        step = existing.get(key) or created.get(key) or models.CampaignStep(type=data["type"])
        step.type = data["type"]
        step.order = data.get("order", i)
        step.message = data.get("message")
        step.delay_hours = data.get("delay_hours")
        parent = data.get("parent_step_id")
        step.parent_step_id = real.get(parent, parent) if parent else None
        step.branch_condition = data.get("branch_condition")
        step.ai_config = data.get("ai_config")
        step.config = data.get("config")
        updated.append(step)
    campaign.steps[:] = updated


MAX_STEPS = 60
MAX_DEPTH = 6


def check_tree(rows: list[dict], types: dict[str, str]) -> None:
    """The steps must form a tree the engine can run: branches hang off conditional steps, a conditional ends its list, and nothing is too big."""
    from fastapi import HTTPException

    from .. import step_types

    def bad(message: str):
        raise HTTPException(status_code=422, detail=[{"loc": ["body", "steps"], "msg": message, "type": "steps.invalid"}])
    if len(rows) > MAX_STEPS:
        bad(f"A sequence can have up to {MAX_STEPS} steps.")
    by_list: dict[tuple, list[dict]] = {}
    parents: dict[str, str | None] = {}
    for data in rows:
        parent = data.get("parent_step_id") or None
        branch = (data.get("branch_condition") or {}).get("branch")
        parent_type = types.get(parent) if parent else None
        if parent and parent not in types:
            bad("A branch points at a step that is not in the sequence.")
        try:
            step_types.check_branch(data["type"], parent_type, data.get("branch_condition"))
        except ValueError as exc:
            bad(str(exc))
        by_list.setdefault((parent, branch), []).append(data)
        parents[data.get("id") or ""] = parent
    for (parent, branch), items in by_list.items():
        items.sort(key=lambda d: d.get("order", 0))
        for item in items[:-1]:
            if item["type"] in step_types.CONDITIONALS:
                bad("An If step must be the last step of its list: what comes next goes inside its yes and no branches.")
    for key in parents:
        depth, seen, node = 0, set(), key
        while parents.get(node):
            if node in seen:
                bad("The branches form a loop.")
            seen.add(node)
            node, depth = parents[node], depth + 1
        if depth > MAX_DEPTH:
            bad(f"Branches can be nested up to {MAX_DEPTH} levels deep.")


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
    shown = display_statuses(db, campaigns)
    return [{**campaign_out(c), "displayStatus": shown[c.id]} for c in campaigns]


def display_statuses(db: Session, campaigns) -> dict[str, str]:
    """The status a person reads on the list: draft, paused, queued, running, no_more_pending, finished, failed or archived."""
    runs: dict[str, dict[str, int]] = {}
    ids = [c.id for c in campaigns if c.status == "active"]
    if ids:
        for campaign_id, status, count in db.query(models.SequenceRun.campaign_id, models.SequenceRun.status, func.count()).filter(
                models.SequenceRun.campaign_id.in_(ids)).group_by(models.SequenceRun.campaign_id, models.SequenceRun.status):
            runs.setdefault(campaign_id, {})[status] = count
    out = {}
    for c in campaigns:
        if c.status != "active":
            out[c.id] = {"completed": "finished"}.get(c.status, c.status)
            continue
        counts = runs.get(c.id, {})
        live = sum(counts.get(k, 0) for k in campaign_settings.ACTIVE_RUN_STATES)
        if not counts:
            out[c.id] = "queued"
        elif live == 0:
            out[c.id] = "no_more_pending"
        elif (c.consecutive_failures or 0) >= 3:
            out[c.id] = "failed"
        else:
            out[c.id] = "running"
    return out


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
    was_paused = campaign.status == "paused"
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
        first_launch = campaign.launched_at is None
        if first_launch:
            campaign.launched_at = datetime.now(timezone.utc)
        engine.launch_campaign(db, campaign)
        if first_launch:
            integrations_core.emit(db, campaign.user_id, "campaign_launched", {"name": campaign.name, "campaign": campaign.name})

    if data.get("status") == "paused" and not was_paused:
        integrations_core.emit(db, campaign.user_id, "campaign_paused", {"name": campaign.name, "campaign": campaign.name, "reason": "Paused by you."})
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


def _duplicate(campaign_id: str, db: Session, user: models.User):
    """A new draft with the same senders, list, schedule, exclusions, AI context and sequence. No runs, no drafts, nothing launched."""
    src = _owned(db, user, campaign_id)
    copy = models.Campaign(
        user_id=user.id, name=f"Copy of {src.name}"[:200], description=src.description, status="draft", account_id=src.account_id,
        account_ids=list(src.account_ids or []), lead_list_id=src.lead_list_id, daily_connection_limit=src.daily_connection_limit,
        daily_message_limit=src.daily_message_limit, timezone=src.timezone, start_hour=src.start_hour, end_hour=src.end_hour,
        working_days=list(src.working_days or []), random_delay=src.random_delay, stop_when_replied=src.stop_when_replied,
        stop_when_accepted=src.stop_when_accepted, ai_personalization=src.ai_personalization, pause_on_failure=src.pause_on_failure,
        audience_source=src.audience_source, week_schedule=src.week_schedule, exclusions=src.exclusions, allocation=src.allocation,
        ai_context=src.ai_context, sequence_mode=src.sequence_mode, graph=src.graph)
    db.add(copy)
    db.flush()
    _apply_steps(copy, [{"id": s.id, "type": s.type, "order": s.order, "message": s.message, "delay_hours": s.delay_hours, "ai_config": s.ai_config, "config": s.config,
                         "parent_step_id": s.parent_step_id, "branch_condition": s.branch_condition} for s in src.steps])
    db.commit()
    db.refresh(copy)
    return campaign_out(copy)


def _import_sequence(body: dict, db: Session, user: models.User):
    """A new draft from a file made by Share sequence: its steps, AI settings and campaign context. No leads, senders or runs come with it."""
    data = body.get("sequence")
    if not isinstance(data, dict) or data.get("synexSequence") != 1 or not isinstance(data.get("steps"), list) or not data["steps"]:
        raise HTTPException(status_code=422, detail="That is not a Synex sequence file. Use a file made with Share sequence.")
    from .. import step_types
    steps = []
    for i, raw in enumerate(data["steps"][:MAX_STEPS]):
        if not isinstance(raw, dict) or not step_types.known(str(raw.get("type"))):
            raise HTTPException(status_code=422, detail=f"Step {i + 1} is not a step Synex knows.")
        branch = raw.get("branch")
        steps.append(_parse(StepIn, {"id": f"s{i}", "type": raw["type"], "order": raw.get("order", i), "message": raw.get("message"), "delayHours": raw.get("delayHours"),
                                     "aiConfig": raw.get("aiConfig"), "config": raw.get("config"),
                                     "parentStepId": f"s{raw['parent']}" if isinstance(raw.get("parent"), int) else None,
                                     "branchCondition": {"branch": branch} if branch else None}))
    created = _create(_parse(CampaignIn, {"name": str(data.get("name") or "Imported sequence")[:200], "aiContext": data.get("aiContext") or {}, "sequenceMode": "classic"}), db, user)
    campaign = _owned(db, user, created["id"])
    _apply_steps(campaign, steps)
    db.commit()
    db.refresh(campaign)
    return campaign_out(campaign)


def _archive(campaign_id: str, db: Session, user: models.User):
    campaign = _owned(db, user, campaign_id)
    if campaign.status in ("draft", "active"):
        raise HTTPException(status_code=409, detail="Pause or finish a campaign before archiving it. A draft can be deleted instead.")
    campaign.status = "archived"
    db.commit()
    return campaign_out(campaign)


@router.get("/{campaign_id}/share")
def share_sequence(campaign_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_data_user)):
    """The sequence as a file to pass to someone else: steps, AI settings and the campaign context, never leads, senders or runs."""
    campaign = _owned(db, user, campaign_id)
    ordered = sorted(campaign.steps, key=lambda x: (x.parent_step_id or "", x.order))
    index_of = {s.id: i for i, s in enumerate(ordered)}
    return {"synexSequence": 1, "name": campaign.name, "sequenceMode": campaign.sequence_mode or "classic", "aiContext": campaign.ai_context or {},
            "steps": [{"type": s.type, "message": s.message, "delayHours": s.delay_hours, "aiConfig": s.ai_config, "config": s.config, "order": s.order,
                       "parent": index_of.get(s.parent_step_id), "branch": (s.branch_condition or {}).get("branch")} for s in ordered]}


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
    if action == "import":
        return _import_sequence(body, db, user)
    if action in ("duplicate", "archive"):
        if not body.get("id"):
            raise HTTPException(status_code=400, detail="id is required")
        return (_duplicate if action == "duplicate" else _archive)(body["id"], db, user)
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
