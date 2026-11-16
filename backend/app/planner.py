"""Dry run: what the engine and worker would do next, without doing it.

Reads state only (no writes, no browser, nothing sent). Account choice, step rules, daily
allowances, per-action limits and hard ceilings, pacing and message rendering reuse the engine's
own functions. A limit of 0 shows as "Paused for this action", never as unlimited. The plan assumes
the engine's fastest pacing (the low end of its random jitter): under that pacing it is
exactly what the engine and worker do, and with any slower jitter every action happens at
or after its planned time. Which account takes a later action can then differ, because the
engine gives each lead to whichever account is free first.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from . import campaign_settings, dnc, engine, models

MAX_ACTIONS = 50
PAUSE_LABELS = {"send_invite": "connection request", "send_message": "message"}
SEARCH_STEP = timedelta(minutes=15)
SEARCH_LIMIT = timedelta(days=14)


@dataclass(frozen=True)
class PlannedAction:
    lead_id: str
    lead_name: str
    account_id: str | None
    account_name: str | None
    step_id: str | None
    step_order: int | None
    step_type: str | None
    task_type: str | None
    message: str
    ai_personalized: bool
    earliest_at: datetime | None
    skip_reason: str | None


@dataclass
class _AccountPlan:
    account: models.LinkedInAccount
    ready_at: datetime  # the account's own cooldown
    slots: list[tuple[datetime, timedelta]] = field(default_factory=list)  # planned times and the pause after each
    kinds: list[tuple[datetime, str]] = field(default_factory=list)  # planned times and their task types

    def capacity_at(self, moment: datetime) -> int:
        """Actions the account can still take on the day (in its own timezone) that `moment` falls on: the
        engine's daily allowance for that day, less what this plan already put there."""
        day = engine._local(moment, engine.account_tz(self.account)).date()
        planned = sum(1 for slot, _ in self.slots if engine._local(slot, engine.account_tz(self.account)).date() == day)
        return engine.remaining_capacity(self.account, moment) - planned

    def type_room_at(self, db: Session, campaign: models.Campaign, ttype: str, moment: datetime) -> int | None:
        """The engine's room for this action type on the account's day that `moment` falls on, less what this plan
        already put on that day (and, for connection requests, in the seven days before `moment`)."""
        zone = engine.account_tz(self.account)
        day = engine._local(moment, zone).date()
        same = [at for at, kind in self.kinds if kind == ttype]
        today = sum(1 for at in same if engine._local(at, zone).date() == day)
        week = sum(1 for at in same if moment - timedelta(days=7) < at <= moment)
        return engine.type_room(db, campaign, self.account, ttype, moment, planned_today=today, planned_week=week)

    def pause_after(self, campaign: models.Campaign, moment: datetime, lead: models.Lead) -> timedelta:
        """The engine's pause after an action at `moment` (its allowance already reduced by that action), at the
        fastest end of its jitter."""
        base = engine.pacing_base(campaign, moment, lead, self.capacity_at(moment) - 1)
        return engine.EXHAUSTED_GAP if base is None else timedelta(seconds=base * engine.GAP_JITTER[0])


def _name(lead: models.Lead) -> str:
    return f"{lead.first_name} {lead.last_name}".strip() or "Unknown"


def _first_action(campaign: models.Campaign, steps: list[models.CampaignStep], lead: models.Lead):
    """(step, task type, hours of waiting before it) for the lead's first real action, or None."""
    waited = 0
    for step in steps:
        if step.type == "end":
            return None
        if step.type == "wait":
            waited += step.delay_hours or 0
        elif step.type == "connection_request":
            if (campaign.audience_source or {}).get("type") != "connections" and lead.status not in engine.ACCEPTED_STATES:
                return step, "send_invite", waited
        elif step.type in ("message", "follow_up"):
            return step, ("send_message" if lead.status in engine.ACCEPTED_STATES else "check_connection"), waited
        elif step.type in engine.ACTION_TASKS:
            return step, engine.ACTION_TASKS[step.type], waited
    return None


def _open_time(campaign: models.Campaign, lead: models.Lead, start: datetime) -> datetime | None:
    moment = start
    while moment - start <= SEARCH_LIMIT:
        if engine.within_hours(campaign, moment, lead):
            return moment
        moment += SEARCH_STEP
    return None


def _slot(plan: _AccountPlan, campaign: models.Campaign, lead: models.Lead, earliest: datetime) -> datetime | None:
    """The first working-hours moment at or after `earliest` when the account is free: past its own cooldown
    and past the pause after every action already planned for it, without crowding one planned later."""
    moment = _open_time(campaign, lead, max(earliest, plan.ready_at))
    for _ in range(len(plan.slots) + 1):
        if moment is None:
            return None
        pause = plan.pause_after(campaign, moment, lead)
        clashes = [slot + after for slot, after in plan.slots if slot <= moment < slot + after or moment < slot < moment + pause]
        if not clashes:
            return moment
        moment = _open_time(campaign, lead, max(clashes))
    return moment


def _slot_with_capacity(db: Session, plan: _AccountPlan, campaign: models.Campaign, lead: models.Lead, earliest: datetime,
                        ttype: str) -> datetime | None:
    """Like `_slot`, but a day with no allowance left, overall or for this action type, pushes the action to the
    account's next day, as the engine does."""
    moment = earliest
    for _ in range(int(SEARCH_LIMIT.days) + 1):
        slot = _slot(plan, campaign, lead, moment)
        if slot is None:
            return None
        room = plan.type_room_at(db, campaign, ttype, slot)
        if plan.capacity_at(slot) > 0 and (room is None or room > 0):
            return slot
        zone_day = engine._local(slot, engine.account_tz(plan.account))
        moment = (zone_day + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(slot.tzinfo)
    return None


def _choose(db: Session, plans: list[_AccountPlan], campaign: models.Campaign, lead: models.Lead, earliest: datetime, ttype: str):
    """The account that can act soonest (ties go to the one with the most capacity left that day, like the engine)."""
    options = [(slot, plan) for plan in plans if (slot := _slot_with_capacity(db, plan, campaign, lead, earliest, ttype)) is not None]
    if not options:
        return None
    soonest = min(slot for slot, _ in options)
    return max(((slot, plan) for slot, plan in options if slot == soonest), key=lambda option: option[1].capacity_at(soonest))


def plan_campaign(db: Session, campaign: models.Campaign, now: datetime, limit: int = MAX_ACTIONS) -> list[PlannedAction]:
    steps = engine.sorted_steps(campaign)
    plans = [
        _AccountPlan(a, max(now, engine._aware(a.next_action_at) or now))
        for a in engine.campaign_accounts(db, campaign) if engine.account_is_live(a, now)
    ]
    leads = sorted(campaign.lead_list.leads if campaign.lead_list else [], key=lambda l: (l.created_at, l.id))[:limit]
    planned: list[PlannedAction] = []
    for lead in leads:
        def skipped(reason: str) -> PlannedAction:
            return PlannedAction(lead.id, _name(lead), None, None, None, None, None, None, "", False, None, reason)

        stop = engine.stop_reason_for(campaign, lead)
        if stop:
            planned.append(skipped(f"Lead is already {stop.replace('_', ' ')}."))
            continue
        if not (lead.linkedin_url or "").strip():
            planned.append(skipped("Lead has no LinkedIn URL."))
            continue
        if dnc.blocked(db, campaign.user_id, lead):
            planned.append(skipped("On the do-not-contact list."))
            continue
        left_out = campaign_settings.exclusion_reason(db, campaign, lead)
        if left_out:
            planned.append(skipped("Left out by this campaign's settings: " + campaign_settings.EXCLUSION_TEXT.get(left_out, left_out) + "."))
            continue
        first = _first_action(campaign, steps, lead)
        if first is None:
            planned.append(skipped("The sequence has nothing to send to this lead."))
            continue
        step, task_type, waited = first
        if engine.campaign_type_limit(campaign, task_type) == 0:
            planned.append(skipped(f"Paused for this action: the campaign's daily {PAUSE_LABELS[task_type]} limit is 0."))
            continue
        if plans and all(engine.configured_daily_limit(p.account) == 0 for p in plans):
            planned.append(skipped("Paused for this action: every connected sender account has a daily limit of 0."))
            continue
        earliest = _open_time(campaign, lead, now + timedelta(hours=waited))
        if earliest is None:
            planned.append(skipped("The campaign's working hours never open."))
            continue
        chosen = _choose(db, plans, campaign, lead, earliest, task_type)
        if chosen is None:
            planned.append(skipped("No connected sender account has capacity left."))
            continue
        at, plan = chosen
        plan.slots.append((at, plan.pause_after(campaign, at, lead)))
        plan.kinds.append((at, task_type))
        if task_type in ("check_connection", "visit_profile", "follow_profile"):
            message, prepared = "", False
        else:
            message, prepared = engine.message_for(db, campaign, step, lead)  # exactly what the engine will send
        planned.append(PlannedAction(lead.id, _name(lead), plan.account.id, plan.account.name, step.id, step.order, step.type,
                                     task_type, message, prepared, at, None))
    return planned
