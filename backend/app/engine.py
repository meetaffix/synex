"""Outreach sequence engine.

The engine decides which step is due for each prospect and queues an
:class:`AgentTask`. The outreach worker (``python -m app.outreach_worker``) claims
those tasks and performs them through the account's server-side browser session
(``app.linkedin_session``), then applies the result (``app.outreach_results``).

Rules enforced here, off real signals and never fabricated:
* reply / interested / not-interested -> stop the sequence
* messages wait until the connection is accepted; a scheduled check detects acceptance
* daily counters roll over in the *account's* timezone; working hours use the
  campaign timezone, or the lead's own timezone when it has one
* per-account daily (with warm-up) and weekly connection-request caps, under the hard ceilings in config;
  a limit of 0 means that action is stopped, never "no limit"
* every task has an idempotency key (run id + step id), so a step is queued once
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from . import campaign_settings, dnc, models, step_types
from .config import DAILY_ACTION_CEILING, DAILY_TYPE_CEILINGS, WEEKLY_INVITE_CEILING, settings
from .providers import render_variables  # the engine never imports an AI provider: it sends finished text only

# Campaign step type -> executor task type.
ACTION_TASKS = step_types.ACTION_TASKS  # profile_visit, follow, like_post, withdraw_invite: one task each, no text

ACCEPTED_STATES = {"connected", "replied", "interested", "not_interested"}
ACTIVE_RUN_STATES = ("running", "waiting_connection", "awaiting_agent", "needs_review")
# Task states that still count against an account's limits.
LIVE_TASK_STATES = ("pending", "running", "done")

# Account warm-up: a freshly-sending account starts at WARMUP_BASE actions/day
# and gains WARMUP_STEP more each day until it reaches the configured limit.
WARMUP_BASE = 5
WARMUP_STEP = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _zone(name: str | None) -> ZoneInfo | None:
    try:
        return ZoneInfo(name) if name else None
    except Exception:  # unknown zone names fall back to UTC
        return None


def _local(now: datetime, tz: str | None) -> datetime:
    zone = _zone(tz)
    return now.astimezone(zone) if zone else now


def account_tz(account: models.LinkedInAccount) -> str:
    """The account's own timezone, fixed with its browser identity at first connect."""
    return (account.browser_profile or {}).get("timezoneId") or "UTC"


def lead_tz(campaign: models.Campaign, lead: models.Lead | None) -> str | None:
    return (lead.timezone if lead and lead.timezone else None) or campaign.timezone


# --------------------------------------------------------------------------
# Control plane
# --------------------------------------------------------------------------
def kill_switch_active(db: Session) -> bool:
    """True when the setting or the admin endpoint has stopped all task execution."""
    if settings.outreach_kill_switch:
        return True
    control = db.get(models.OutreachControl, "global")
    return bool(control and control.kill_switch)


# --------------------------------------------------------------------------
# Activity audit trail
# --------------------------------------------------------------------------
def record_event(
    db: Session,
    lead: "models.Lead",
    type_: str,
    detail: str | None = None,
    campaign: "models.Campaign | None" = None,
    account: "models.LinkedInAccount | None" = None,
    step_id: str | None = None,
    task_id: str | None = None,
) -> None:
    """Append one immutable history entry for a lead. Never raises into callers."""
    if lead is None:
        return
    db.add(
        models.LeadEvent(
            user_id=lead.user_id,
            lead_id=lead.id,
            campaign_id=(campaign.id if campaign else lead.campaign_id),
            account_id=account.id if account else None,
            type=type_,
            detail=detail,
            step_id=step_id,
            task_id=task_id,
        )
    )


def _retry_later(now: datetime) -> datetime:
    return now + timedelta(hours=1)


# --------------------------------------------------------------------------
# Steps
# --------------------------------------------------------------------------
def sorted_steps(campaign: models.Campaign) -> list[models.CampaignStep]:
    return sorted(campaign.steps, key=lambda s: s.order)


def _branch(step: models.CampaignStep) -> str | None:
    return (step.branch_condition or {}).get("branch")


def first_in_list(steps: list[models.CampaignStep], parent_id: str | None, branch: str | None) -> models.CampaignStep | None:
    """The first step of one list: the main sequence (no parent) or one branch (yes or no) of a conditional step."""
    items = sorted((s for s in steps if s.parent_step_id == parent_id and _branch(s) == branch), key=lambda s: s.order)
    return items[0] if items else None


def current_step(steps: list[models.CampaignStep], run: models.SequenceRun) -> models.CampaignStep | None:
    """The run's step, looked up by id so steps can be added to a live campaign."""
    if run.current_step_id is None:
        return first_in_list(steps, None, None) if steps and run.status != "completed" else None
    return next((s for s in steps if s.id == run.current_step_id), None)


def next_step(steps: list[models.CampaignStep], step: models.CampaignStep) -> models.CampaignStep | None:
    """The step after this one in its own list. A branch that runs out of steps ends the run, so there is no jump back to the main list."""
    items = sorted((s for s in steps if s.parent_step_id == step.parent_step_id and _branch(s) == _branch(step)), key=lambda s: s.order)
    return next((s for s in items if s.order > step.order), None)


def _complete(run: models.SequenceRun, now: datetime) -> None:
    run.current_step_id, run.status, run.stop_reason, run.completed_at = None, "completed", "ended", now


def _enter(run: models.SequenceRun, step: models.CampaignStep, now: datetime) -> None:
    run.current_step_id, run.status, run.next_action_at, run.step_entered_at = step.id, "running", now, now


def move_past(steps: list[models.CampaignStep], run: models.SequenceRun, step: models.CampaignStep, now: datetime) -> None:
    following = next_step(steps, step)
    if following is None:
        _complete(run, now)
        return
    _enter(run, following, now)


def take_branch(steps: list[models.CampaignStep], run: models.SequenceRun, conditional: models.CampaignStep, branch: str, now: datetime) -> None:
    """Continue a run down the yes or no branch of a conditional step; an empty branch ends it."""
    first = first_in_list(steps, conditional.id, branch)
    if first is None:
        _complete(run, now)
        return
    _enter(run, first, now)


def lead_is_active(db: Session, lead: models.Lead, now: datetime, days: int) -> bool:
    """Active means Synex has recorded something from this person in the last `days` days: a reply, a message or an accepted invitation. LinkedIn's own
    "active" signal needs the profile reader and is not used (built, unverified on real LinkedIn)."""
    since = now - timedelta(days=days)
    if lead.connected_at is not None and _aware(lead.connected_at) >= since:
        return True
    return db.query(models.LeadEvent.id).filter(models.LeadEvent.lead_id == lead.id, models.LeadEvent.created_at >= since,
                                                models.LeadEvent.type.in_(("replied", "reply_received", "message_received", "connected", "accepted"))).first() is not None


def step_order_of(steps: list[models.CampaignStep], run: models.SequenceRun) -> int | None:
    step = current_step(steps, run)
    return step.order if step else None


# --------------------------------------------------------------------------
# Launch
# --------------------------------------------------------------------------
def launch_campaign(db: Session, campaign: models.Campaign) -> int:
    """Create a SequenceRun for every lead in the campaign's list (idempotent)."""
    if not campaign.lead_list:
        return 0
    existing = {r.lead_id for r in db.query(models.SequenceRun).filter(models.SequenceRun.campaign_id == campaign.id).all()}
    steps = sorted_steps(campaign)
    root = first_in_list(steps, None, None)
    first = root.id if root else None
    now = _now()
    created = 0
    excluded: dict[str, int] = {}
    for index, lead in enumerate(sorted(campaign.lead_list.leads, key=lambda l: (l.created_at, l.id))):
        if lead.campaign_id is None:
            lead.campaign_id = campaign.id
        if lead.id in existing:
            continue
        reason = "do_not_contact" if dnc.blocked(db, campaign.user_id, lead) else campaign_settings.exclusion_reason(db, campaign, lead)
        if reason:  # on the do-not-contact list, or left out by this campaign's exclusion settings: never started
            excluded[reason] = excluded.get(reason, 0) + 1
            record_event(db, lead, "excluded", campaign_settings.EXCLUSION_TEXT.get(reason, reason), campaign=campaign)
            continue
        db.add(
            models.SequenceRun(
                user_id=campaign.user_id, campaign_id=campaign.id, lead_id=lead.id,
                current_step_id=first, status="running", next_action_at=now, step_entered_at=now,
                started_at=now + timedelta(microseconds=index),  # a stable processing order
            )
        )
        record_event(db, lead, "added_to_campaign", campaign.name, campaign=campaign)
        created += 1
    previous = (campaign.launch_summary or {}).get("excluded", {}) if campaign.launch_summary else {}
    campaign.launch_summary = {"enrolled": len(existing) + created, "excluded": {k: previous.get(k, 0) + v for k, v in excluded.items()} if excluded else previous}
    return created


# --------------------------------------------------------------------------
# Liveness, limits & schedule
# --------------------------------------------------------------------------
def account_is_live(account: models.LinkedInAccount | None, now: datetime | None = None) -> bool:
    """Live means the saved browser session is connected and the account is not paused."""
    return account is not None and account.status == "active" and account.session_status == "connected"


def _roll_daily_window(account: models.LinkedInAccount, now: datetime) -> None:
    """Reset the daily counters when the account crosses into a new day in its own timezone."""
    today = _local(now, account_tz(account)).date().isoformat()
    if account.last_action_date != today:
        account.last_action_date = today
        account.daily_actions_used = 0
        account.messages_today = 0
        account.connections_today = 0


def _reserve_daily(account: models.LinkedInAccount, now: datetime) -> None:
    _roll_daily_window(account, now)
    account.daily_actions_used = (account.daily_actions_used or 0) + 1
    if account.warmup_started_at is None:
        account.warmup_started_at = now  # anchor the warm-up ramp to the first real action


def refund_daily(account: models.LinkedInAccount | None) -> None:
    if account and account.daily_actions_used:
        account.daily_actions_used = max(0, account.daily_actions_used - 1)


def configured_daily_limit(account: models.LinkedInAccount) -> int:
    """The account's own daily limit, held under the hard ceiling. 0 means stopped; unset means the ceiling."""
    if account.daily_action_limit is None:
        return DAILY_ACTION_CEILING
    return max(0, min(account.daily_action_limit, DAILY_ACTION_CEILING))


def effective_daily_limit(account: models.LinkedInAccount, now: datetime) -> int:
    """The account's daily cap after warm-up: day 0 = 5, +5/day, up to the configured limit (0 stays 0)."""
    ceiling = configured_daily_limit(account)
    start = _aware(account.warmup_started_at)
    if start is None:
        return min(ceiling, WARMUP_BASE)
    days = max((now - start).days, 0)
    return min(ceiling, WARMUP_BASE + days * WARMUP_STEP)


def remaining_capacity(account: models.LinkedInAccount, now: datetime) -> int:
    """Actions the account can still perform today (in its own timezone), after warm-up."""
    today = _local(now, account_tz(account)).date().isoformat()
    used = account.daily_actions_used if account.last_action_date == today else 0
    return effective_daily_limit(account, now) - (used or 0)


def campaign_accounts(db: Session, campaign: models.Campaign) -> list[models.LinkedInAccount]:
    """The campaign's sending-account pool: the primary plus any extras."""
    ids: list[str] = []
    if campaign.account_id:
        ids.append(campaign.account_id)
    for aid in campaign.account_ids or []:
        if aid and aid not in ids:
            ids.append(aid)
    accounts = [db.get(models.LinkedInAccount, aid) for aid in ids]
    return [a for a in accounts if a is not None]


def _account_ready(account: models.LinkedInAccount, now: datetime) -> bool:
    nxt = _aware(account.next_action_at)
    return nxt is None or nxt <= now


def pick_account(accounts: list[models.LinkedInAccount], now: datetime) -> models.LinkedInAccount | None:
    """Load-balance: the live, off-cooldown account with the most remaining daily capacity."""
    candidates = [a for a in accounts if account_is_live(a, now) and remaining_capacity(a, now) > 0 and _account_ready(a, now)]
    return max(candidates, key=lambda a: remaining_capacity(a, now)) if candidates else None


def within_hours(campaign: models.Campaign, now: datetime, lead: models.Lead | None = None) -> bool:
    """Is now inside the working days/hours, in the lead's timezone when it has one?"""
    local = _local(now, lead_tz(campaign, lead))
    if getattr(campaign, "week_schedule", None):
        window = campaign_settings.day_window(campaign, local)
        return window is not None and window[0] <= local.hour * 60 + local.minute < window[1]
    days = campaign.working_days or []
    if days and ((local.weekday() + 1) % 7) not in days:  # 0=Sun..6=Sat
        return False
    if campaign.start_hour is not None and campaign.end_hour is not None:
        return campaign.start_hour <= local.hour < campaign.end_hour
    return True


GAP_JITTER = (0.7, 1.3)  # human pacing: each gap is its base times a random factor in this range
EXHAUSTED_GAP = timedelta(minutes=30)


def pacing_base(campaign: models.Campaign, now: datetime, lead: models.Lead | None, remaining: int) -> float | None:
    """The gap before an account's next action, in seconds, before jitter: the day's remaining quota spread
    across the rest of the working window, clamped to 45s-20min. None when the account has no quota left."""
    if remaining <= 0:
        return None
    local = _local(now, lead_tz(campaign, lead))
    end_hour = campaign.end_hour if campaign.end_hour is not None else 18
    if getattr(campaign, "week_schedule", None):
        window = campaign_settings.day_window(campaign, local)
        if window is not None:
            end_hour = -(-window[1] // 60)  # round the day's end up to a whole hour
    end_local = local.replace(hour=min(max(end_hour, local.hour + 1), 23), minute=0, second=0, microsecond=0)
    secs_left = max((end_local - local).total_seconds(), 60 * 60)
    return max(45.0, min(secs_left / remaining, 20 * 60))


def _action_gap(campaign: models.Campaign, account: models.LinkedInAccount, now: datetime, lead: models.Lead | None) -> timedelta:
    """Spread the day's remaining quota across the working window — never a burst. Jittered +-30%."""
    base = pacing_base(campaign, now, lead, remaining_capacity(account, now))
    if base is None:
        return EXHAUSTED_GAP
    return timedelta(seconds=base * random.uniform(*GAP_JITTER))


def _park_until(campaign: models.Campaign, accounts: list[models.LinkedInAccount], now: datetime, lead: models.Lead | None) -> datetime:
    """When a send is blocked, the soonest sensible time to re-evaluate."""
    if not within_hours(campaign, now, lead):
        return _retry_later(now)
    ready = [_aware(a.next_action_at) for a in accounts
             if account_is_live(a, now) and remaining_capacity(a, now) > 0 and _aware(a.next_action_at)]
    future = [t for t in ready if t and t > now]
    return min(future) if future else _retry_later(now)


def _day_start_utc(account: models.LinkedInAccount, now: datetime) -> datetime:
    local = _local(now, account_tz(account))
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def weekly_invites(db: Session, account: models.LinkedInAccount, now: datetime) -> int:
    """Invitations queued or sent by this account in the last seven days."""
    return (
        db.query(models.AgentTask)
        .filter(
            models.AgentTask.account_id == account.id,
            models.AgentTask.type == "send_invite",
            models.AgentTask.status.in_(LIVE_TASK_STATES),
            models.AgentTask.created_at >= now - timedelta(days=7),
        )
        .count()
    )


# The campaign field holding the campaign's own daily limit for a task type.
CAMPAIGN_LIMIT_FIELDS = {"send_invite": "daily_connection_limit", "send_message": "daily_message_limit"}


def weekly_invite_cap() -> int:
    """The weekly connection-request cap: the setting, never above the hard ceiling."""
    return max(0, min(settings.outreach_weekly_connection_limit, WEEKLY_INVITE_CEILING))


def campaign_type_limit(campaign: models.Campaign, ttype: str) -> int | None:
    """The campaign's own daily limit for this action, held under the hard ceiling. 0 means the action is
    paused; unset means the ceiling. None when the campaign has no limit field for the action."""
    field = CAMPAIGN_LIMIT_FIELDS.get(ttype)
    if field is None:
        return None
    value, ceiling = getattr(campaign, field), DAILY_TYPE_CEILINGS[ttype]
    return ceiling if value is None else max(0, min(value, ceiling))


def _count_today(db: Session, account: models.LinkedInAccount, ttype: str, now: datetime,
                 campaign: models.Campaign | None = None) -> int:
    """Tasks of this type queued or done by the account since its local midnight (for one campaign, or all)."""
    query = db.query(models.AgentTask).filter(
        models.AgentTask.account_id == account.id,
        models.AgentTask.type == ttype,
        models.AgentTask.status.in_(LIVE_TASK_STATES),
        models.AgentTask.created_at >= _day_start_utc(account, now),
    )
    if campaign is not None:
        query = query.join(models.SequenceRun, models.AgentTask.sequence_run_id == models.SequenceRun.id).filter(
            models.SequenceRun.campaign_id == campaign.id)
    return query.count()


def type_room(db: Session, campaign: models.Campaign, account: models.LinkedInAccount, ttype: str, now: datetime,
              planned_today: int = 0, planned_week: int = 0) -> int | None:
    """How many more actions of this type the campaign may queue on the account on `now`'s day (in the account's
    timezone): the least of the hard daily ceiling (counting every campaign), the weekly invite cap and the
    campaign's own limit. The dry run passes what it has already planned. None when the type has no cap."""
    from .account_policy import action_room
    rooms = [action_room(db, account, ttype, now) - planned_today]
    ceiling = DAILY_TYPE_CEILINGS.get(ttype)
    if ceiling is not None:
        rooms.append(ceiling - _count_today(db, account, ttype, now) - planned_today)
    from . import plans
    cap = plans.daily_cap(db, account.user_id, ttype)  # what the workspace's plan allows each account in a day
    if cap is not None:
        rooms.append(cap - _count_today(db, account, ttype, now) - planned_today)
    if ttype == "send_invite":
        rooms.append(weekly_invite_cap() - weekly_invites(db, account, now) - planned_week)
    limit = campaign_type_limit(campaign, ttype)
    if limit is not None:
        rooms.append(limit - _count_today(db, account, ttype, now, campaign) - planned_today)
    reserved = ((getattr(campaign, "allocation", None) or {}).get(account.id) or {}).get(ttype)
    if reserved is not None:  # this campaign's own daily slice of the sender's day
        rooms.append(min(reserved, DAILY_TYPE_CEILINGS.get(ttype, reserved)) - _count_today(db, account, ttype, now, campaign) - planned_today)
    return min(rooms) if rooms else None


def _type_limit_reached(db: Session, campaign: models.Campaign, account: models.LinkedInAccount, ttype: str, now: datetime) -> bool:
    room = type_room(db, campaign, account, ttype, now)
    return room is not None and room <= 0


def manual_send_refusal(db: Session, account: models.LinkedInAccount, ttype: str, now: datetime) -> str | None:
    """Why a person's own send (an inbox reply) cannot be queued on this account now, or None when it can."""
    from .account_policy import action_room
    if account.status in ("deactivated", "archived", "deleted"):
        return "This sender seat is inactive. Reactivate it before sending."
    if configured_daily_limit(account) == 0:
        return "This account's daily limit is 0, so it is paused. Raise the limit under Sender accounts to send from it."
    if action_room(db, account, ttype, now) <= 0:
        from .account_policy import bounds
        return f"This account has reached its limit of {bounds(account, ttype, now)[2]} for this action in the last 24 hours."
    ceiling = DAILY_TYPE_CEILINGS.get(ttype)
    if ceiling is not None and _count_today(db, account, ttype, now) >= ceiling:
        return f"This account has reached its hard ceiling of {ceiling} messages today. It can send again tomorrow."
    return None


# --------------------------------------------------------------------------
# Inbox side effects (used by the executor's results)
# --------------------------------------------------------------------------
def get_or_create_convo(db: Session, campaign, lead, account, now) -> models.Conversation:
    convo = (
        db.query(models.Conversation)
        .filter(models.Conversation.user_id == lead.user_id, models.Conversation.lead_id == lead.id)
        .first()
    )
    if convo is None:
        convo = models.Conversation(
            user_id=lead.user_id, lead_id=lead.id,
            campaign_id=campaign.id if campaign else None,
            account_id=account.id if account else None,
            status="active", last_message_preview="", last_message_at=now, unread=False,
        )
        db.add(convo)
        db.flush()
    return convo


def record_outbound(db: Session, campaign, lead, account, body: str, now: datetime, task_id: str | None = None) -> None:
    convo = get_or_create_convo(db, campaign, lead, account, now)
    db.add(models.Message(conversation_id=convo.id, direction="outbound", body=body, sent_at=now, read=True, task_id=task_id))
    convo.last_message_preview = body
    convo.last_message_at = now
    convo.unread = False


# --------------------------------------------------------------------------
# Task emission
# --------------------------------------------------------------------------
def emit_task(
    db: Session, account: models.LinkedInAccount, ttype: str, payload: dict, key: str,
    run: models.SequenceRun | None = None,
) -> models.AgentTask | None:
    """Queue a task unless one with this idempotency key already exists. The unique
    index backs this up when two processes race."""
    if db.query(models.AgentTask.id).filter_by(idempotency_key=key).first():
        return None
    ceiling = DAILY_TYPE_CEILINGS.get(ttype)
    if ceiling is None:  # a type with no hard ceiling must never reach LinkedIn
        raise ValueError(f"task type {ttype!r} has no daily ceiling in config.DAILY_TYPE_CEILINGS")
    from .account_policy import action_room
    if account.status in ("deactivated", "archived", "deleted") or action_room(db, account, ttype, _now()) <= 0:
        return None
    task = models.AgentTask(
        account_id=account.id, sequence_run_id=run.id if run else None, type=ttype,
        payload=payload, status="pending", idempotency_key=key, version=0, created_at=_now(),
    )
    db.add(task)
    db.flush()  # the session does not autoflush: later limit counts in this same tick must see this task
    return task


def _emit_for_run(db, campaign, run, step, ttype, lead, message, account, now, extra: dict | None = None) -> None:
    from .providers import render_sender_variables
    message = render_sender_variables(message, account)  # the sender is known only now, when an account is picked
    payload = {"leadId": lead.id, "linkedinUrl": lead.linkedin_url or "", "message": message or "",
               "stepId": step.id, "campaignId": campaign.id, **(extra or {})}
    task = emit_task(db, account, ttype, payload, f"{run.id}:{step.id}", run)
    if task is not None:
        _reserve_daily(account, now)
    run.status = "awaiting_agent"
    run.next_action_at = now + timedelta(hours=24)  # parked; the task result reschedules


def _send_or_park(db, campaign, run, step, ttype, lead, message, accounts, now, extra: dict | None = None) -> None:
    """Queue a task on a ready account that still has room for this action type, or park the run until it can act."""
    open_accounts = [a for a in accounts if not _type_limit_reached(db, campaign, a, ttype, now)]
    account = pick_account(open_accounts, now)
    if account is None or not within_hours(campaign, now, lead):
        run.next_action_at = _park_until(campaign, open_accounts, now, lead)
        return
    _emit_for_run(db, campaign, run, step, ttype, lead, message, account, now, extra)
    account.next_action_at = now + _action_gap(campaign, account, now, lead)  # human pacing


def stop_run(run: models.SequenceRun, reason: str, now: datetime) -> None:
    run.status = "stopped"
    run.stop_reason = reason
    run.completed_at = now


def message_for(db: Session, campaign: models.Campaign, step: models.CampaignStep, lead: models.Lead) -> tuple[str, bool]:
    """The finished text to send, and whether it is a prepared draft. Never calls an AI service.

    The approved draft for this lead and step if there is one (prepared before launch, see ``drafts.py``); otherwise
    the step's template with variables and spintax. Sending, the dry run and the planner all use this one function.
    """
    draft = (
        db.query(models.LeadDraft)
        .filter_by(campaign_id=campaign.id, step_id=step.id, lead_id=lead.id, status="approved")
        .first()
    )
    if draft is not None:
        return draft.body, True
    return render_variables(step.message, lead), False


def _schedule_after(campaign: models.Campaign, now: datetime, hours: int | None, minutes: int | None = None) -> datetime:
    total = minutes if minutes else (hours or 0) * 60
    base = now + timedelta(minutes=total)
    if campaign.random_delay:
        base += timedelta(minutes=random.randint(0, min(30, total // 4)))  # human-like jitter, never larger than the wait itself
    return base


def stop_reason_for(campaign: models.Campaign, lead: models.Lead) -> str | None:
    """Why a lead's sequence must stop, from the lead's real state."""
    if lead.status in ("interested", "not_interested", "bounced"):
        return lead.status
    if lead.status == "replied" and campaign.stop_when_replied:
        return "replied"
    if campaign.stop_when_accepted and lead.status in ACCEPTED_STATES:
        return "accepted"
    return None


def _await_acceptance(db, campaign, run, step, lead, accounts, now) -> None:
    """The lead has not accepted yet: poll LinkedIn on a slow schedule (counted against limits)."""
    run.status = "waiting_connection"
    interval = timedelta(hours=settings.outreach_acceptance_check_interval_hours)
    last = _aware(run.last_acceptance_check_at)
    if last is not None and now - last < interval:
        run.next_action_at = last + interval
        return
    account = pick_account(accounts, now)
    if account is None or not within_hours(campaign, now, lead):
        run.next_action_at = _park_until(campaign, accounts, now, lead)
        return
    payload = {"leadId": lead.id, "linkedinUrl": lead.linkedin_url or "", "stepId": step.id, "campaignId": campaign.id}
    task = emit_task(db, account, "check_connection", payload, f"{run.id}:{step.id}:check:{now.isoformat()}", run)
    if task is not None:
        _reserve_daily(account, now)
        run.last_acceptance_check_at = now
    run.status = "awaiting_agent"
    run.next_action_at = now + timedelta(hours=24)
    account.next_action_at = now + _action_gap(campaign, account, now, lead)


def _branch_and_continue(db, campaign, steps, run, conditional, branch, accounts, now) -> None:
    """Take a branch and start its first step in the same tick, so a decision does not cost an extra wait."""
    take_branch(steps, run, conditional, branch, now)
    if run.status == "running":
        _advance_run(db, campaign, steps, run, accounts, now)


def _advance_run(db: Session, campaign, steps, run, accounts, now) -> None:
    lead = run.lead
    if lead is None:
        stop_run(run, "lead_removed", now)
        return
    reason = stop_reason_for(campaign, lead)
    if reason:
        stop_run(run, reason, now)
        return
    if dnc.blocked(db, campaign.user_id, lead):
        stop_run(run, "do_not_contact", now)
        return

    if not (lead.linkedin_url or "").strip():
        stop_run(run, "no_linkedin_url", now)
        return

    step = current_step(steps, run)
    if step is None:
        if run.current_step_id is None:
            run.status, run.stop_reason, run.completed_at = "completed", "ended", now
        else:
            stop_run(run, "step_removed", now)
        return
    if step.type == "end":
        run.status, run.stop_reason, run.completed_at, run.current_step_id = "completed", "ended", now, None
        return

    if step.type == "wait":
        move_past(steps, run, step, now)
        run.next_action_at = _schedule_after(campaign, now, step.delay_hours, step_types.wait_minutes(step))
        return

    if step.type == "if_connected":
        connected = lead.status in ACCEPTED_STATES or (campaign.audience_source or {}).get("type") == "connections"
        if connected:
            _branch_and_continue(db, campaign, steps, run, step, "yes", accounts, now)
            return
        days = (step.config or {}).get("waitDays", step_types.DEFAULT_CONNECTION_WAIT_DAYS)
        deadline = (_aware(run.step_entered_at) or _aware(run.started_at) or now) + timedelta(days=days)
        if now >= deadline:  # not accepted in time: the "not connected" branch
            _branch_and_continue(db, campaign, steps, run, step, "no", accounts, now)
            return
        _await_acceptance(db, campaign, run, step, lead, accounts, now)
        if run.next_action_at is not None and _aware(run.next_action_at) > deadline and run.status == "waiting_connection":
            run.next_action_at = deadline
        return

    if step.type == "if_active":
        days = (step.config or {}).get("days", step_types.DEFAULT_ACTIVE_DAYS)
        _branch_and_continue(db, campaign, steps, run, step, "yes" if lead_is_active(db, lead, now, days) else "no", accounts, now)
        return

    if step.type == "connection_request":
        # Skip when already connected, or when the audience is "My connections".
        if (campaign.audience_source or {}).get("type") == "connections" or lead.status in ACCEPTED_STATES:
            move_past(steps, run, step, now)
            return
        _send_or_park(db, campaign, run, step, "send_invite", lead, message_for(db, campaign, step, lead)[0], accounts, now)
        return

    if step.type in ("message", "follow_up"):
        if lead.status not in ACCEPTED_STATES:
            _await_acceptance(db, campaign, run, step, lead, accounts, now)
            return
        _send_or_park(db, campaign, run, step, "send_message", lead, message_for(db, campaign, step, lead)[0], accounts, now)
        return

    if step.type in ("inmail", "free_inmail"):
        text = message_for(db, campaign, step, lead)[0]
        extra = {"subject": (step.config or {}).get("subject", ""), "free": step.type == "free_inmail"}
        _send_or_park(db, campaign, run, step, "send_inmail", lead, text, accounts, now, extra)
        return

    if step.type == "voice_note":
        if lead.status not in ACCEPTED_STATES:
            _await_acceptance(db, campaign, run, step, lead, accounts, now)
            return
        config = step.config or {}
        if not config.get("audioId"):
            stop_run(run, "voice_note_missing", now)
            return
        _send_or_park(db, campaign, run, step, "send_voice_note", lead, "", accounts, now, {"audioId": config["audioId"]})
        return

    if step.type in ACTION_TASKS:
        _send_or_park(db, campaign, run, step, ACTION_TASKS[step.type], lead, "", accounts, now)
        return

    move_past(steps, run, step, now)  # unknown step type: skip it


# --------------------------------------------------------------------------
# Inbox sync scheduling
# --------------------------------------------------------------------------
def emit_stale_withdrawals(db: Session, now: datetime, per_tick: int = 3) -> int:
    """For senders that switched on auto-withdraw: take back connection requests that stayed unanswered longer than the chosen number of days.
    A few at a time, inside the withdraw_invite ceiling and the account's own policy; never an invitation that has been accepted."""
    from .account_policy import action_room, policy_for
    emitted = 0
    for account in db.query(models.LinkedInAccount).filter(models.LinkedInAccount.status == "active", models.LinkedInAccount.session_status == "connected").all():
        policy = policy_for(account)
        if not policy.auto_withdraw:
            continue
        cutoff = now - timedelta(days=policy.stale_invite_days)
        room = min(per_tick, action_room(db, account, "withdraw_invite", now))
        if room <= 0:
            continue
        rows = (db.query(models.AgentTask, models.SequenceRun.lead_id).join(models.SequenceRun, models.AgentTask.sequence_run_id == models.SequenceRun.id)
                .filter(models.AgentTask.account_id == account.id, models.AgentTask.type == "send_invite", models.AgentTask.status == "done",
                        models.AgentTask.committed_at.isnot(None), models.AgentTask.committed_at <= cutoff).order_by(models.AgentTask.committed_at).limit(200).all())
        for task, lead_id in rows:
            if room <= 0:
                break
            lead = db.get(models.Lead, lead_id)
            if lead is None or lead.connected_at is not None or lead.status in ACCEPTED_STATES or not (lead.linkedin_url or "").strip():
                continue
            made = emit_task(db, account, "withdraw_invite", {"leadId": lead.id, "linkedinUrl": lead.linkedin_url}, f"withdraw:{account.id}:{lead.id}")
            if made is not None:
                emitted += 1
                room -= 1
    return emitted


def emit_inbox_syncs(db: Session, now: datetime) -> int:
    """Queue one inbox read per live account when its interval has elapsed (and one right after connecting).
    sync_mode decides what is STORED (outreach_results.apply_inbox), not whether the inbox is read."""
    interval = timedelta(minutes=settings.outreach_inbox_sync_interval_minutes)
    queued = 0
    for account in db.query(models.LinkedInAccount).filter(models.LinkedInAccount.session_status == "connected").all():
        if not account_is_live(account):
            continue
        last = _aware(account.last_inbox_sync_at)
        if last is not None and now - last < interval:
            continue
        open_sync = db.query(models.AgentTask.id).filter(
            models.AgentTask.account_id == account.id, models.AgentTask.type == "sync_inbox",
            models.AgentTask.status.in_(["pending", "running"]),
        ).first()
        if open_sync:  # reading the inbox is not outreach: it never depends on the outreach daily limit or on sync_mode
            continue
        if emit_task(db, account, "sync_inbox", {}, f"inbox:{account.id}:{now.isoformat()}"):
            queued += 1
    return queued


# --------------------------------------------------------------------------
# Tick
# --------------------------------------------------------------------------
def tick(db: Session) -> dict:
    from .routers.inbox import release_due
    release_due(db, _now())  # scheduled replies whose time has come, each checked against the sender's limits
    emit_stale_withdrawals(db, _now())
    """Process all due sequence runs once, queueing tasks for the worker to execute."""
    if kill_switch_active(db):
        return {"processed": 0, "killed": True}
    now = _now()
    processed = 0

    for campaign in db.query(models.Campaign).filter(models.Campaign.status == "active").all():
        steps = sorted_steps(campaign)
        if not steps:
            continue
        accounts = campaign_accounts(db, campaign)
        runs = (
            db.query(models.SequenceRun)
            .filter(models.SequenceRun.campaign_id == campaign.id, models.SequenceRun.status.in_(["running", "waiting_connection"]))
            .order_by(models.SequenceRun.started_at, models.SequenceRun.id)
            .all()
        )
        for run in runs:
            if run.next_action_at is None or _aware(run.next_action_at) <= now:
                _advance_run(db, campaign, steps, run, accounts, now)
                processed += 1

        total = db.query(models.SequenceRun).filter(models.SequenceRun.campaign_id == campaign.id).count()
        active = (
            db.query(models.SequenceRun)
            .filter(models.SequenceRun.campaign_id == campaign.id, models.SequenceRun.status.in_(ACTIVE_RUN_STATES))
            .count()
        )
        if total > 0 and active == 0:
            campaign.status = "completed"

    queued_syncs = emit_inbox_syncs(db, now)
    db.commit()
    return {"processed": processed, "inboxSyncs": queued_syncs}
