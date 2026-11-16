"""The dashboard's three feeds: summary, time series and per-account numbers.

Every number is counted from real rows: invitations are tasks of type send_invite that finished (status done),
accepted connections are leads with a connected_at date, replies are inbound messages. With no data the numbers are zero.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import median

from sqlalchemy.orm import Session

from . import models
from .analytics import _aware


@dataclass(frozen=True)
class FeedFilters:
    since: datetime | None = None
    until: datetime | None = None
    campaign_id: str | None = None
    account_id: str | None = None

    def covers(self, when: datetime | None) -> bool:
        when = _aware(when)
        if when is None:
            return self.since is None and self.until is None
        return (self.since is None or when >= self.since) and (self.until is None or when <= self.until)


def _invitations(db: Session, user_id: str, f: FeedFilters) -> list[tuple[str, str, datetime | None]]:
    """Invitations that were really sent: (lead id, account id, when)."""
    query = (
        db.query(models.AgentTask, models.SequenceRun)
        .join(models.SequenceRun, models.AgentTask.sequence_run_id == models.SequenceRun.id)
        .filter(models.SequenceRun.user_id == user_id, models.AgentTask.type == "send_invite", models.AgentTask.status == "done")
    )
    if f.campaign_id:
        query = query.filter(models.SequenceRun.campaign_id == f.campaign_id)
    if f.account_id:
        query = query.filter(models.AgentTask.account_id == f.account_id)
    return [(run.lead_id, task.account_id, _aware(task.committed_at or task.updated_at)) for task, run in query.all()]


def _conversations(db: Session, user_id: str, f: FeedFilters) -> list[models.Conversation]:
    query = db.query(models.Conversation).filter(models.Conversation.user_id == user_id)
    if f.campaign_id:
        query = query.filter(models.Conversation.campaign_id == f.campaign_id)
    if f.account_id:
        query = query.filter(models.Conversation.account_id == f.account_id)
    return query.all()


_EARLIEST = datetime.min.replace(tzinfo=timezone.utc)


def _inbound(conversation: models.Conversation) -> list[models.Message]:
    return sorted((m for m in conversation.messages if m.direction == "inbound"), key=lambda m: _aware(m.sent_at) or _EARLIEST)


def _response_seconds(conversation: models.Conversation) -> float | None:
    """From the first inbound message to the next outbound message after it, when there is one."""
    inbound = _inbound(conversation)
    first = _aware(inbound[0].sent_at) if inbound else None
    if first is None:
        return None
    later = [_aware(m.sent_at) for m in conversation.messages if m.direction == "outbound" and _aware(m.sent_at) and _aware(m.sent_at) >= first]
    return (min(later) - first).total_seconds() if later else None


def _leads(db: Session, lead_ids: set[str]) -> dict[str, models.Lead]:
    return {l.id: l for l in db.query(models.Lead).filter(models.Lead.id.in_(lead_ids))} if lead_ids else {}


def summary(db: Session, user_id: str, f: FeedFilters) -> dict:
    invites = _invitations(db, user_id, f)
    contacted = {lead_id for lead_id, _, when in invites if f.covers(when)}
    leads = _leads(db, {lead_id for lead_id, _, _ in invites})
    accepted = sum(1 for l in leads.values() if l.connected_at and f.covers(l.connected_at))
    conversations = _conversations(db, user_id, f)
    replies = sum(1 for c in conversations for m in _inbound(c) if f.covers(m.sent_at))
    interested = [c for c in conversations if (c.status == "interested" or c.interest in ("interested", "meeting_booked")) and f.covers(c.last_message_at)]
    answered = [c for c in interested if _response_seconds(c) is not None]
    times = [t for c in conversations if (t := _response_seconds(c)) is not None and f.covers(_inbound(c)[0].sent_at)]
    return {
        "connectionsAccepted": accepted,
        "leadsContacted": len(contacted),
        "replies": replies,
        "interestedLeads": len(interested),
        "interestedAnswered": len(answered),
        "medianResponseSeconds": float(median(times)) if times else None,
    }


def timeseries(db: Session, user_id: str, f: FeedFilters, granularity: str = "week") -> dict:
    def bucket(when: datetime) -> datetime:
        day = _aware(when).replace(hour=0, minute=0, second=0, microsecond=0)
        return day - timedelta(days=day.weekday()) if granularity == "week" else day

    counts: dict[datetime, dict[str, int]] = defaultdict(lambda: {"requests": 0, "accepted": 0, "replies": 0})
    invites = _invitations(db, user_id, f)
    for _, _, when in invites:
        if when and f.covers(when):
            counts[bucket(when)]["requests"] += 1
    for lead in _leads(db, {lead_id for lead_id, _, _ in invites}).values():
        if lead.connected_at and f.covers(lead.connected_at):
            counts[bucket(lead.connected_at)]["accepted"] += 1
    for conversation in _conversations(db, user_id, f):
        for message in _inbound(conversation):
            if message.sent_at and f.covers(message.sent_at):
                counts[bucket(message.sent_at)]["replies"] += 1
    if not counts:
        return {"points": []}
    step = timedelta(days=7 if granularity == "week" else 1)
    first = bucket(f.since) if f.since else min(counts)
    last = bucket(f.until) if f.until else max(max(counts), bucket(datetime.now(timezone.utc)))
    points, cursor = [], first
    while cursor <= last and len(points) < 400:
        points.append({"date": cursor.date().isoformat(), **counts.get(cursor, {"requests": 0, "accepted": 0, "replies": 0})})
        cursor += step
    return {"points": points}


def accounts(db: Session, user_id: str, f: FeedFilters) -> list[dict]:
    by_account: dict[str, set[str]] = defaultdict(set)
    sent: dict[str, int] = defaultdict(int)
    for lead_id, account_id, when in _invitations(db, user_id, f):
        if f.covers(when):
            by_account[account_id].add(lead_id)
            sent[account_id] += 1
    leads = _leads(db, {lead_id for ids in by_account.values() for lead_id in ids})
    conversations = _conversations(db, user_id, f)
    result = []
    for account_id in sorted(by_account):
        contacted = by_account[account_id]
        accepted = sum(1 for lead_id in contacted if leads.get(lead_id) and leads[lead_id].connected_at)
        replied = sum(1 for c in conversations if c.account_id == account_id and c.lead_id in contacted and _inbound(c))
        result.append({
            "accountId": account_id,
            "requestsSent": sent[account_id],
            "acceptedPercent": round(accepted / len(contacted) * 100, 1),
            "leadsContacted": len(contacted),
            "replyPercent": round(replied / len(contacted) * 100, 1),
        })
    return result


INTERESTED = ("interested", "meeting_booked")


def _is_interested(c: models.Conversation) -> bool:
    return c.status == "interested" or c.interest in INTERESTED


def _stage_counts(db: Session, user_id: str, f: FeedFilters) -> dict[str, int]:
    runs = db.query(models.SequenceRun.lead_id).filter(models.SequenceRun.user_id == user_id)
    if f.campaign_id:
        runs = runs.filter(models.SequenceRun.campaign_id == f.campaign_id)
    in_campaign = {lead_id for (lead_id,) in runs}
    invites = _invitations(db, user_id, f)
    contacted = {lead_id for lead_id, _, when in invites if f.covers(when)}
    leads = _leads(db, contacted)
    accepted = {lead_id for lead_id in contacted if leads.get(lead_id) and leads[lead_id].connected_at and f.covers(leads[lead_id].connected_at)}
    conversations = _conversations(db, user_id, f)
    replied = {c.lead_id for c in conversations if any(f.covers(m.sent_at) for m in _inbound(c))}
    interested = {c.lead_id for c in conversations if _is_interested(c) and f.covers(c.last_message_at)}
    return {"leads": len(in_campaign), "contacted": len(contacted), "accepted": len(accepted), "replied": len(replied), "interested": len(interested)}


def funnel(db: Session, user_id: str, f: FeedFilters) -> dict:
    """Leads in campaigns, then how many were contacted, accepted, replied and were interested. Each step also says what share of the one before it."""
    counts = _stage_counts(db, user_id, f)
    stages = [("leads", "In campaigns"), ("contacted", "Contacted"), ("accepted", "Accepted"), ("replied", "Replied"), ("interested", "Interested")]
    out, previous = [], None
    for key, label in stages:
        value = counts[key]
        out.append({"key": key, "label": label, "count": value, "percentOfPrevious": round(100 * value / previous, 1) if previous else None})
        previous = value
    return {"stages": out}


def campaigns(db: Session, user_id: str, f: FeedFilters) -> list[dict]:
    rows = []
    query = db.query(models.Campaign).filter_by(user_id=user_id)
    if f.campaign_id:
        query = query.filter(models.Campaign.id == f.campaign_id)
    for campaign in query.order_by(models.Campaign.name).all():
        counts = _stage_counts(db, user_id, FeedFilters(f.since, f.until, campaign.id, f.account_id))
        rows.append({"campaignId": campaign.id, "name": campaign.name, "status": campaign.status, **counts,
                     "acceptedPercent": round(100 * counts["accepted"] / counts["contacted"], 1) if counts["contacted"] else None,
                     "replyPercent": round(100 * counts["replied"] / counts["accepted"], 1) if counts["accepted"] else None})
    return rows
