"""Campaign settings beyond the sequence: the weekly schedule, who is left out, how each sender's day is shared, and the AI context.

Validation lives here so the API, the engine and the launch check agree. Nothing in this module talks to LinkedIn or an AI provider.
"""
from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy.orm import Session

from . import models
from .config import DAILY_TYPE_CEILINGS
from .dedup import normalize_linkedin_url

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
EXCLUSION_KEYS = ("other_campaigns", "reached_other_campaigns", "reached_same_sender", "messaged_other_senders", "existing_connections")
ALLOCATABLE = ("send_invite", "send_message", "visit_profile")  # like_post joins when that action exists
CONTEXT_LIMIT = 5000
CONTEXT_TEXT_KEYS = ("goals", "meeting_link", "qualification_questions", "proof_points", "objections", "do_not_mention", "notes", "website")
ACTIVE_RUN_STATES = ("running", "waiting_connection", "awaiting_agent", "needs_review")

DEFAULT_WEEK = {day: {"on": day in DAYS[:5], "start": "08:00", "end": "20:00"} for day in DAYS}
DEFAULT_EXCLUSIONS = {key: False for key in EXCLUSION_KEYS}


def _minutes(value: str) -> int:
    return int(value[:2]) * 60 + int(value[3:])


def check_week_schedule(value: dict | None) -> dict | None:
    """{'mon': {'on': True, 'start': '08:00', 'end': '20:00'}, ...}: every day present, times valid, start before end, at least one day on."""
    if value is None:
        return None
    if set(value) != set(DAYS):
        raise ValueError("The schedule needs one entry for each weekday: " + ", ".join(DAYS) + ".")
    out = {}
    for day in DAYS:
        entry = value[day]
        if not isinstance(entry, dict) or not isinstance(entry.get("on"), bool):
            raise ValueError(f"{day}: say whether the day is on or off.")
        start, end = entry.get("start", "08:00"), entry.get("end", "20:00")
        if not (isinstance(start, str) and isinstance(end, str) and _TIME.match(start) and _TIME.match(end)):
            raise ValueError(f"{day}: times must look like 08:00.")
        if entry["on"] and _minutes(start) >= _minutes(end):
            raise ValueError(f"{day}: the start time must be before the end time.")
        out[day] = {"on": entry["on"], "start": start, "end": end}
    if not any(entry["on"] for entry in out.values()):
        raise ValueError("Turn on at least one day.")
    return out


def day_window(campaign, local: datetime) -> tuple[int, int] | None:
    """Minutes since midnight [start, end) that sending is allowed on this local day; None when the day is off. None for a campaign without a weekly schedule."""
    schedule = getattr(campaign, "week_schedule", None)
    if not schedule:
        raise LookupError("no weekly schedule")
    entry = schedule.get(DAYS[local.weekday()])
    if not entry or not entry.get("on"):
        return None
    return _minutes(entry["start"]), _minutes(entry["end"])


def check_exclusions(value: dict | None) -> dict | None:
    if value is None:
        return None
    unknown = set(value) - set(EXCLUSION_KEYS)
    if unknown:
        raise ValueError("Unknown exclusion: " + ", ".join(sorted(unknown)) + ".")
    if any(not isinstance(v, bool) for v in value.values()):
        raise ValueError("Each exclusion is on or off.")
    return {key: bool(value.get(key, False)) for key in EXCLUSION_KEYS}


def check_allocation(value: dict | None) -> dict | None:
    """{account_id: {action: daily number}}. Each number is 0 to that action's hard ceiling; an unlisted action is not reserved."""
    if value is None:
        return None
    out = {}
    for account_id, actions in value.items():
        if not isinstance(actions, dict):
            raise ValueError("Each sender needs a set of action numbers.")
        row = {}
        for action, number in actions.items():
            if action not in ALLOCATABLE:
                raise ValueError(f"'{action}' cannot be reserved. Choose from: {', '.join(ALLOCATABLE)}.")
            ceiling = DAILY_TYPE_CEILINGS.get(action, 0)
            if not isinstance(number, int) or isinstance(number, bool) or number < 0 or number > ceiling:
                raise ValueError(f"{action}: use a whole number from 0 to {ceiling}, the hard maximum.")
            row[action] = number
        out[str(account_id)] = row
    return out


def check_ai_context(value: dict | None) -> dict | None:
    """Shared knowledge for every AI message and reply in this campaign. Text fields are capped; lists are lists of short strings."""
    if value is None:
        return None
    out: dict = {}
    for key in CONTEXT_TEXT_KEYS:
        item = value.get(key)
        if item is None:
            continue
        if key in ("do_not_mention",):
            if not isinstance(item, list) or any(not isinstance(x, str) or len(x) > 200 for x in item) or len(item) > 50:
                raise ValueError("Do not mention: a list of up to 50 short phrases.")
            out[key] = [x.strip() for x in item if x.strip()]
        else:
            if not isinstance(item, str) or len(item) > CONTEXT_LIMIT:
                raise ValueError(f"{key}: text of at most {CONTEXT_LIMIT} characters.")
            out[key] = item
    if "audience" in value and isinstance(value["audience"], str):
        out["audience"] = value["audience"][:CONTEXT_LIMIT]
    return out


def campaign_account_ids(campaign) -> set[str]:
    return {i for i in [campaign.account_id, *(campaign.account_ids or [])] if i}


def exclusion_reason(db: Session, campaign: models.Campaign, lead: models.Lead) -> str | None:
    """Why this lead is left out of the campaign by its exclusion settings; None when they may start."""
    ex = campaign.exclusions or {}
    if not any(ex.get(k) for k in EXCLUSION_KEYS):
        return None
    mine = campaign_account_ids(campaign)
    runs = db.query(models.SequenceRun).filter(models.SequenceRun.lead_id == lead.id, models.SequenceRun.campaign_id != campaign.id).all()
    if ex.get("other_campaigns") and any(r.status in ACTIVE_RUN_STATES for r in runs):
        return "in_other_campaign"
    if ex.get("reached_other_campaigns") and (runs or lead.status not in ("new", None)):
        return "reached_by_other_campaign"
    if ex.get("reached_same_sender") or ex.get("messaged_other_senders"):
        tasks = (db.query(models.AgentTask.account_id, models.AgentTask.type)
                 .join(models.SequenceRun, models.AgentTask.sequence_run_id == models.SequenceRun.id)
                 .filter(models.SequenceRun.lead_id == lead.id, models.SequenceRun.campaign_id != campaign.id, models.AgentTask.status == "done",
                         models.AgentTask.type.in_(("send_invite", "send_message"))).all())
        if ex.get("reached_same_sender") and any(a in mine for a, _ in tasks):
            return "reached_by_same_sender"
        if ex.get("messaged_other_senders") and any(a not in mine and t == "send_message" for a, t in tasks):
            return "messaged_by_other_sender"
    if ex.get("existing_connections"):
        if lead.connection_degree == 1 or lead.status in ("connected", "replied", "interested", "not_interested"):
            return "already_connected"
        key = normalize_linkedin_url(lead.linkedin_url)
        if key and mine and db.query(models.AccountConnection.id).filter(models.AccountConnection.account_id.in_(mine), models.AccountConnection.kind == "connection",
                                                                            models.AccountConnection.url_key == key).first():
            return "already_connected"
    return None


EXCLUSION_TEXT = {
    "in_other_campaign": "already in another running campaign",
    "reached_by_other_campaign": "already reached through another campaign",
    "reached_by_same_sender": "already reached by the same sender",
    "messaged_by_other_sender": "already messaged by another sender",
    "already_connected": "already a connection",
    "do_not_contact": "on the do-not-contact list",
}
