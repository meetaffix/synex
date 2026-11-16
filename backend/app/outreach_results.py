"""Applies what the outreach worker did to the database: lead and run state, counters,
the inbox, and the audit trail. All functions are synchronous and take their own
short-lived session so they can run from the worker's browser thread via
``asyncio.to_thread``. Message bodies are stored on messages and events but never logged.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from sqlalchemy import delete, or_
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from . import engine, models
from .config import settings
from .database import SessionLocal
from .linkedin_session import store
from .linkedin_session.actions import InboundConversation

log = logging.getLogger("synex.outreach")

PAUSE_REASONS = {
    "logged_out": "LinkedIn signed this account out. Reconnect it to resume sending.",
    "checkpoint": "LinkedIn asked for a security check. Complete it on LinkedIn, then reconnect this account.",
    "restricted": "LinkedIn restricted this account. Resolve it on LinkedIn, then reconnect this account.",
}


@dataclass
class TaskContext:
    db: Session
    task: models.AgentTask
    account: models.LinkedInAccount
    run: models.SequenceRun | None
    campaign: models.Campaign | None
    lead: models.Lead | None
    steps: list[models.CampaignStep]
    step: models.CampaignStep | None
    now: datetime


def _context(db: Session, task: models.AgentTask) -> TaskContext:
    run = task.sequence_run
    campaign = run.campaign if run else None
    payload = task.payload or {}
    lead = run.lead if run else (db.get(models.Lead, payload.get("leadId")) if payload.get("leadId") else None)
    steps = engine.sorted_steps(campaign) if campaign else []
    step = next((s for s in steps if s.id == payload.get("stepId")), None)
    return TaskContext(db, task, task.account, run, campaign, lead, steps, step, engine._now())  # the engine's clock: one time source


def release_key(task: models.AgentTask) -> None:
    """Free the idempotency key of a task that did not act, so its step can be queued again."""
    task.idempotency_key = f"{task.idempotency_key}:released:{uuid.uuid4().hex[:8]}"


# ------------------------------------------------------------------ claims

def acquire_lease(db: Session, account_id: str, holder: str, now: datetime) -> bool:
    """Take (or renew) the account's browser lease with one conditional upsert. It succeeds only when no
    lease exists, the existing one has expired, or the caller already holds it, so two workers can never
    both hold it; the database decides, not a separate check."""
    insert = postgres_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    expires = now + timedelta(seconds=settings.outreach_lease_seconds)
    statement = insert(models.AccountLease).values(account_id=account_id, holder=holder, expires_at=expires)
    statement = statement.on_conflict_do_update(
        index_elements=[models.AccountLease.account_id], set_={"holder": holder, "expires_at": expires},
        where=or_(models.AccountLease.expires_at < now, models.AccountLease.holder == holder))
    won = db.execute(statement).rowcount == 1
    db.commit()
    return won


def release_lease(db: Session, account_id: str, holder: str) -> None:
    db.execute(delete(models.AccountLease).where(models.AccountLease.account_id == account_id, models.AccountLease.holder == holder))
    db.commit()


def claim_next_task(db: Session, account_id: str, worker_id: str, now: datetime) -> str | None:
    """Atomically claim the account's oldest runnable task. The caller must hold the account's lease (this
    renews it), and exactly one caller can win a given task: the UPDATE only matches while the task is
    still pending at the version read."""
    if not acquire_lease(db, account_id, worker_id, now):
        return None  # another worker holds this account: one browser per account at a time
    candidates = (
        db.query(models.AgentTask.id, models.AgentTask.version)
        .filter(models.AgentTask.account_id == account_id, models.AgentTask.status == "pending",
                (models.AgentTask.next_attempt_at.is_(None)) | (models.AgentTask.next_attempt_at <= now))
        .order_by(models.AgentTask.created_at).limit(5).all()
    )
    for task_id, version in candidates:
        won = db.query(models.AgentTask).filter(
            models.AgentTask.id == task_id, models.AgentTask.status == "pending", models.AgentTask.version == version,
        ).update({"status": "running", "claimed_by": worker_id, "claimed_at": now, "version": version + 1,
                  "attempts": models.AgentTask.attempts + 1}, synchronize_session=False)
        db.commit()
        if won:
            return task_id
    return None


def unclaim_task(task_id: str, worker_id: str) -> None:
    """Give back a task this worker claimed but never started (the lease was lost first). A task whose
    irreversible click was reached (committed_at set) is left alone for the stale-task sweep."""
    with SessionLocal() as db:
        db.query(models.AgentTask).filter(
            models.AgentTask.id == task_id, models.AgentTask.status == "running", models.AgentTask.claimed_by == worker_id,
            models.AgentTask.committed_at.is_(None),
        ).update({"status": "pending", "claimed_by": None, "claimed_at": None, "version": models.AgentTask.version + 1,
                  "attempts": models.AgentTask.attempts - 1}, synchronize_session=False)
        db.commit()


def mark_committed(task_id: str) -> None:
    # Re-read after navigation as the owner may have stopped an action while the page loaded.
    reason = precheck(task_id)
    if reason:
        raise PolicyChanged(reason)
    with SessionLocal() as db:
        db.query(models.AgentTask).filter_by(id=task_id).update({"committed_at": datetime.now(timezone.utc)})
        db.commit()


def sweep_stale_tasks(db: Session, now: datetime) -> int:
    """A task still running long after its claim belonged to a worker that died. It is never
    retried: it needs a person to check LinkedIn first."""
    cutoff = now - timedelta(seconds=settings.outreach_stale_task_seconds)
    stale = db.query(models.AgentTask).filter(models.AgentTask.status == "running", models.AgentTask.claimed_at < cutoff).all()
    swept = 0
    for task in stale:
        moved = db.query(models.AgentTask).filter(
            models.AgentTask.id == task.id, models.AgentTask.status == "running", models.AgentTask.version == task.version,
        ).update({"status": "needs_review", "version": task.version + 1,
                  "result": {"result": "needs_review", "reason": "worker_interrupted"}}, synchronize_session=False)
        db.commit()
        if moved:
            db.expire_all()
            _after_review(db, db.get(models.AgentTask, task.id), "worker_interrupted")
            swept += 1
    return swept


# ------------------------------------------------------------------ audit

def _audit(ctx: TaskContext, result: str, status: str = "ok", event: str | None = None) -> None:
    """One agent_activity row and one lead event per executed action: account, campaign, step, result."""
    task = ctx.task
    db = ctx.db
    db.add(models.AgentActivity(
        account_id=ctx.account.id, user_id=ctx.account.user_id, scope="task", step=task.type, status=status,
        message=f"{task.type}: {result}", campaign_id=ctx.campaign.id if ctx.campaign else None,
        step_id=ctx.step.id if ctx.step else None, task_id=task.id, result=result))
    if ctx.lead is not None:
        engine.record_event(db, ctx.lead, event or f"action_{result}", f"{task.type}: {result}",
                            campaign=ctx.campaign, account=ctx.account,
                            step_id=ctx.step.id if ctx.step else None, task_id=task.id)


def register_failure(campaign: models.Campaign | None) -> None:
    if campaign is None:
        return
    campaign.consecutive_failures = (campaign.consecutive_failures or 0) + 1
    if (campaign.pause_on_failure and campaign.status == "active"
            and campaign.consecutive_failures >= settings.outreach_max_consecutive_failures):
        campaign.status = "paused"
        campaign.paused_reason = f"Paused automatically after {campaign.consecutive_failures} failed actions in a row."


def _register_success(campaign: models.Campaign | None) -> None:
    if campaign is not None:
        campaign.consecutive_failures = 0


# ------------------------------------------------------------------ pre-check

class PolicyChanged(Exception):
    """A queued action became ineligible before its irreversible click."""


def precheck(task_id: str) -> str | None:
    """Re-read current state just before acting. Returns a reason to skip, or None to proceed."""
    with SessionLocal() as db:
        ctx = _context(db, db.get(models.AgentTask, task_id))
        task, run, lead, campaign = ctx.task, ctx.run, ctx.lead, ctx.campaign
        from .account_policy import action_room
        if ctx.account is None or ctx.account.status in ("deactivated", "archived", "deleted"):
            return "sender_inactive"
        if action_room(db, ctx.account, task.type, ctx.now, exclude_task=task.id) <= 0:
            return "sender_action_limit"
        if task.type in ("send_message", "send_invite", "follow_profile") and engine.configured_daily_limit(ctx.account) == 0:
            return "sender_stopped"
        if run is not None:
            if campaign is None or campaign.status != "active":
                return "campaign_not_active"
            if run.status != "awaiting_agent":
                return "run_not_waiting"
            reason = engine.stop_reason_for(campaign, lead) if lead else "lead_removed"
            if reason:
                return f"lead_{reason}"
        if task.type == "send_invite" and lead and lead.status in engine.ACCEPTED_STATES:
            return "already_connected"
        if task.type == "send_message":
            if db.query(models.Message.id).filter_by(task_id=task.id).first():
                return "already_sent"
            message = db.get(models.Message, (task.payload or {}).get("messageId") or "")
            if message is not None and message.delivery_status == "sent":
                return "already_sent"
        return None


def skip_task(task_id: str, reason: str) -> None:
    with SessionLocal() as db:
        ctx = _context(db, db.get(models.AgentTask, task_id))
        ctx.task.status, ctx.task.result = "cancelled", {"result": "skipped", "reason": reason}
        release_key(ctx.task)
        if ctx.task.type != "sync_inbox":
            engine.refund_daily(ctx.account)
        if ctx.run is not None and ctx.run.status == "awaiting_agent":
            ctx.run.status, ctx.run.next_action_at = "running", ctx.now
        _audit(ctx, f"skipped_{reason}", "warn", "action_skipped")
        db.commit()


# ------------------------------------------------------------------ results

def _count(account: models.LinkedInAccount, now: datetime, field: str) -> None:
    engine._roll_daily_window(account, now)
    setattr(account, field, (getattr(account, field) or 0) + 1)
    total = "connections_sent" if field == "connections_today" else "messages_sent"
    setattr(account, total, (getattr(account, total) or 0) + 1)
    account.last_sync_at = now


def _advance(ctx: TaskContext) -> None:
    if ctx.run is not None and ctx.step is not None:
        engine.move_past(ctx.steps, ctx.run, ctx.step, ctx.now)


def _stop(ctx: TaskContext, reason: str) -> None:
    if ctx.run is not None:
        engine.stop_run(ctx.run, reason, ctx.now)


def _retry_step(ctx: TaskContext, delay: timedelta) -> None:
    """The action did not happen: cancel the task, free its key, and let the engine decide again."""
    ctx.task.status = "cancelled"
    release_key(ctx.task)
    engine.refund_daily(ctx.account)
    if ctx.run is not None:
        ctx.run.status, ctx.run.next_action_at = "running", ctx.now + delay


def _invite(ctx: TaskContext, result: str) -> str | None:
    lead = ctx.lead
    if result == "sent":
        if lead and lead.status == "new":
            lead.status = "contacted"
        _count(ctx.account, ctx.now, "connections_today")
        _advance(ctx)
        return "connection_sent"
    if result in ("already_connected", "already_pending"):
        if lead and lead.status in ("new", "contacted"):
            lead.status = "connected" if result == "already_connected" else "contacted"
        engine.refund_daily(ctx.account)
        _advance(ctx)
        return "connected" if result == "already_connected" else "invite_pending"
    if result == "weekly_limit_reached":
        _retry_step(ctx, timedelta(hours=24))
        ctx.account.next_action_at = ctx.now + timedelta(hours=24)
        return "invite_limit"
    engine.refund_daily(ctx.account)
    _stop(ctx, result)  # note_too_long | profile_unavailable
    return None


def _message(ctx: TaskContext, result: str) -> str | None:
    payload, lead = ctx.task.payload or {}, ctx.lead
    manual = None
    if payload.get("messageId"):
        manual = ctx.db.get(models.Message, payload["messageId"])
    if result == "sent":
        if manual is not None:
            manual.delivery_status, manual.delivery_error, manual.task_id = "sent", None, ctx.task.id
        elif lead is not None:
            engine.record_outbound(ctx.db, ctx.campaign, lead, ctx.account, payload.get("message", ""), ctx.now, ctx.task.id)
        _count(ctx.account, ctx.now, "messages_today")
        _advance(ctx)
        return "message_sent"
    if result == "not_connected":
        if lead and lead.status == "connected":
            lead.status = "contacted"
        if manual is not None:
            manual.delivery_status, manual.delivery_error = "failed", "You are not connected to this person on LinkedIn."
            ctx.task.status = "cancelled"
            release_key(ctx.task)
            engine.refund_daily(ctx.account)
        else:
            _retry_step(ctx, timedelta(0))
            if ctx.run is not None:
                ctx.run.status = "waiting_connection"
        return None
    engine.refund_daily(ctx.account)  # profile_unavailable
    if manual is not None:
        manual.delivery_status, manual.delivery_error = "failed", "This LinkedIn profile is not available."
    _stop(ctx, result)
    return None


def _visit(ctx: TaskContext, result: str) -> str | None:
    if result == "visited":
        _advance(ctx)
        return "profile_visited"
    _stop(ctx, result)
    return None


def _follow(ctx: TaskContext, result: str) -> str | None:
    if result in ("followed", "already_following"):
        _advance(ctx)
        return "followed"
    _stop(ctx, result)
    return None


def _check(ctx: TaskContext, result: str) -> str | None:
    lead, run = ctx.lead, ctx.run
    interval = timedelta(hours=settings.outreach_acceptance_check_interval_hours)
    if result == "connected":
        if lead and lead.status in ("new", "contacted"):
            lead.status = "connected"
        if run is not None:
            run.status, run.next_action_at = "running", ctx.now
        return "connected"
    if result == "pending" and run is not None:
        run.status, run.next_action_at = "waiting_connection", ctx.now + interval
    elif result == "not_connected" and run is not None:
        if lead and lead.status == "contacted":
            _stop(ctx, "invite_withdrawn")
        else:
            run.status, run.next_action_at = "waiting_connection", ctx.now + interval
    else:
        _stop(ctx, result)
    return None


HANDLERS = {"send_invite": _invite, "send_message": _message, "visit_profile": _visit,
            "follow_profile": _follow, "check_connection": _check,
            "collect_leads": lambda ctx, result: None}


def apply_result(task_id: str, result: str) -> None:
    with SessionLocal() as db:
        ctx = _context(db, db.get(models.AgentTask, task_id))
        event = HANDLERS[ctx.task.type](ctx, result)
        if ctx.task.status == "running":
            ctx.task.status = "done"
        ctx.task.result = {"result": result}
        _register_success(ctx.campaign)
        _audit(ctx, result, "ok", event)
        db.commit()
    log.info("outreach task %s %s", task_id, result)


# ------------------------------------------------------------------ failures

def _after_review(db: Session, task: models.AgentTask, reason: str) -> None:
    ctx = _context(db, task)
    if ctx.run is not None:
        ctx.run.status = "needs_review"
    if (task.payload or {}).get("messageId"):
        message = db.get(models.Message, task.payload["messageId"])
        if message is not None:
            message.delivery_status = "failed"
            message.delivery_error = "Delivery could not be confirmed. Check LinkedIn before sending again."
    register_failure(ctx.campaign)
    _audit(ctx, f"needs_review_{reason}", "error", "needs_review")
    db.commit()
    log.warning("outreach task %s needs review: %s", task.id, reason)


def fail_task(task_id: str, reason: str) -> None:
    """A non-session error. After the irreversible step it needs review and is never retried;
    before it, the task retries with backoff up to the attempt limit, then fails for good."""
    with SessionLocal() as db:
        task = db.get(models.AgentTask, task_id)
        now = engine._now()
        if task.committed_at is not None:
            task.status, task.result = "needs_review", {"result": "needs_review", "reason": reason}
            _after_review(db, task, reason)
            return
        ctx = _context(db, task)
        if (task.attempts or 0) < settings.outreach_task_max_attempts:
            delay = settings.outreach_task_retry_backoff_seconds * 2 ** max((task.attempts or 1) - 1, 0)
            task.status, task.claimed_by, task.next_attempt_at = "pending", None, now + timedelta(seconds=delay)
            task.version = (task.version or 0) + 1
            _audit(ctx, f"retry_{reason}", "warn", "action_retry")
        else:
            task.status, task.result = "failed", {"result": "failed", "reason": reason}
            engine.refund_daily(ctx.account)
            if ctx.run is not None:
                engine.stop_run(ctx.run, "send_failed", now)
            register_failure(ctx.campaign)
            _audit(ctx, f"failed_{reason}", "error", "action_failed")
        db.commit()
    log.warning("outreach task %s failed before acting: %s", task_id, reason)


def handle_session_error(account_id: str, task_id: str | None, kind: str) -> None:
    """Stop the account: logged out or checkpoint -> needs_reconnect, restricted -> restricted."""
    with SessionLocal() as db:
        account = db.get(models.LinkedInAccount, account_id)
        store.apply_status(account, "restricted" if kind == "restricted" else "needs_reconnect")
        account.paused_reason = PAUSE_REASONS[kind]
        account.last_checked_at = datetime.now(timezone.utc)
        if task_id:
            task = db.get(models.AgentTask, task_id)
            if task.committed_at is not None:
                task.status, task.result = "needs_review", {"result": "needs_review", "reason": kind}
                _after_review(db, task, kind)
            else:
                task.status, task.claimed_by = "pending", None
                task.attempts = max((task.attempts or 1) - 1, 0)
                task.version = (task.version or 0) + 1
                _audit(_context(db, task), f"session_{kind}", "error", "session_problem")
        db.commit()
    log.warning("outreach account %s stopped: %s", account_id, kind)


# ------------------------------------------------------------------ inbox

def _path(url: str) -> str:
    return urlsplit(url).path.rstrip("/").lower()


def _contacted_by_synex(db: Session, lead: models.Lead) -> bool:
    return (
        lead.status != "new"
        or db.query(models.SequenceRun.id).filter_by(lead_id=lead.id).first() is not None
        or db.query(models.LeadEvent.id).filter(models.LeadEvent.lead_id == lead.id,
                                                models.LeadEvent.type.in_(["connection_sent", "message_sent"])).first() is not None
    )


def _first_outreach_at(db: Session, lead: models.Lead) -> datetime | None:
    first = (db.query(models.LeadEvent.created_at)
             .filter(models.LeadEvent.lead_id == lead.id, models.LeadEvent.type.in_(["connection_sent", "message_sent"]))
             .order_by(models.LeadEvent.created_at).first())
    return engine._aware(first[0]) if first else None


def _stop_runs_on_reply(db: Session, lead: models.Lead, now: datetime) -> None:
    for run in db.query(models.SequenceRun).filter(models.SequenceRun.lead_id == lead.id,
                                                   models.SequenceRun.status.in_(engine.ACTIVE_RUN_STATES)).all():
        if run.campaign and run.campaign.stop_when_replied:
            engine.stop_run(run, "replied", now)


def _store_thread(db: Session, account: models.LinkedInAccount, lead: models.Lead, conv: InboundConversation, now: datetime) -> None:
    convo = engine.get_or_create_convo(db, lead.campaign, lead, account, now)
    convo.li_conversation_id = convo.li_conversation_id or conv.thread_id
    known = {m.li_event_id for m in convo.messages if m.li_event_id}
    since = _first_outreach_at(db, lead)
    for raw in sorted(conv.messages, key=lambda m: m.sent_at):
        if raw.event_id in known:
            continue
        sent_at = datetime.fromisoformat(raw.sent_at)
        inbound = raw.direction == "in"
        mine = next((m for m in convo.messages if m.direction == "outbound" and not m.li_event_id and m.body.strip() == raw.text), None)
        if not inbound and mine is not None:
            mine.li_event_id = raw.event_id  # our own send, now matched to LinkedIn's event
            continue
        db.add(models.Message(conversation_id=convo.id, direction="inbound" if inbound else "outbound", body=raw.text,
                              sent_at=sent_at, read=not inbound, li_event_id=raw.event_id))
        convo.last_message_preview, convo.last_message_at = raw.text, sent_at
        if inbound:
            convo.unread = True
            if since is not None and sent_at > since:
                if lead.status in ("new", "contacted", "connected"):
                    lead.status = "replied"
                engine.record_event(db, lead, "replied", raw.text[:140], campaign=lead.campaign, account=account)
                _stop_runs_on_reply(db, lead, now)


def apply_inbox(task_id: str, conversations: list[InboundConversation]) -> None:
    """Store conversations the account's syncMode allows: `synex_only` keeps only threads with
    leads Synex has contacted; `all` imports everything, creating leads for unknown people."""
    with SessionLocal() as db:
        task = db.get(models.AgentTask, task_id)
        account, now = task.account, engine._now()
        leads = db.query(models.Lead).filter_by(user_id=account.user_id).all()
        by_path = {_path(lead.linkedin_url): lead for lead in leads if lead.linkedin_url}
        stored = 0
        for conv in conversations:
            lead = by_path.get(_path(conv.profile_url))
            if account.sync_mode != "all" and (lead is None or not _contacted_by_synex(db, lead)):
                continue
            if lead is None:
                slug = _path(conv.profile_url).rsplit("/", 1)[-1].replace("-", " ").title() or "LinkedIn member"
                lead = models.Lead(user_id=account.user_id, first_name=slug, last_name="", linkedin_url=conv.profile_url,
                                   source="inbox_sync", status="contacted")
                db.add(lead)
                db.flush()
            _store_thread(db, account, lead, conv, now)
            stored += 1
        account.last_inbox_sync_at = now
        task.status, task.result = "done", {"result": "synced", "conversations": stored}
        db.add(models.AgentActivity(account_id=account.id, user_id=account.user_id, scope="task", step="sync_inbox",
                                    status="ok", message=f"sync_inbox: {stored} conversations", task_id=task.id,
                                    result=f"synced_{stored}"))
        db.commit()
