"""Analytics derived entirely from real database rows.

There are no fabricated numbers here: every value is computed from the user's
actual leads, campaigns, conversations, and messages. When there is no data
yet, the figures are simply zero.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from . import models
from .serializers import (
    CONNECTED_STATES,
    INVITED_STATES,
    REPLIED_STATES,
    campaign_stats,
)

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _aware(dt: datetime | None) -> datetime | None:
    """SQLite may return naive datetimes; coerce them to UTC for comparison."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _pct_change(recent: int, previous: int) -> float:
    if previous == 0:
        return 0.0
    return round((recent - previous) / previous * 100, 1)


def _user_leads(db: Session, user_id: str) -> list[models.Lead]:
    return db.query(models.Lead).filter(models.Lead.user_id == user_id).all()


def _user_campaigns(db: Session, user_id: str) -> list[models.Campaign]:
    return db.query(models.Campaign).filter(models.Campaign.user_id == user_id).all()


def _user_messages(db: Session, user_id: str) -> list[models.Message]:
    return (
        db.query(models.Message)
        .join(models.Conversation, models.Message.conversation_id == models.Conversation.id)
        .filter(models.Conversation.user_id == user_id)
        .all()
    )


# --------------------------------------------------------------------------
# Time series
# --------------------------------------------------------------------------
def build_series(db: Session, user_id: str) -> list[dict]:
    """30-day outreach time series from real message and lead activity."""
    messages = _user_messages(db, user_id)
    leads = _user_leads(db, user_id)
    today = datetime.now(timezone.utc).date()

    invites_by_day: dict = defaultdict(int)
    replies_by_day: dict = defaultdict(int)
    for m in messages:
        d = _aware(m.sent_at)
        if not d:
            continue
        if m.direction == "outbound":
            invites_by_day[d.date()] += 1
        elif m.direction == "inbound":
            replies_by_day[d.date()] += 1

    connections_by_day: dict = defaultdict(int)
    for lead in leads:
        if lead.status in CONNECTED_STATES:
            d = _aware(lead.updated_at)
            if d:
                connections_by_day[d.date()] += 1

    points = []
    for i in range(29, -1, -1):
        day = today - timedelta(days=i)
        points.append(
            {
                "date": day.isoformat(),
                "invites": invites_by_day.get(day, 0),
                "connections": connections_by_day.get(day, 0),
                "replies": replies_by_day.get(day, 0),
            }
        )
    return points


def reply_rate_by_day(db: Session, user_id: str) -> list[dict]:
    """Reply rate per weekday = inbound / outbound messages sent that weekday."""
    messages = _user_messages(db, user_id)
    outbound: dict = defaultdict(int)
    inbound: dict = defaultdict(int)
    for m in messages:
        d = _aware(m.sent_at)
        if not d:
            continue
        weekday = d.weekday()  # 0 = Monday
        if m.direction == "outbound":
            outbound[weekday] += 1
        elif m.direction == "inbound":
            inbound[weekday] += 1

    result = []
    for weekday, label in enumerate(WEEKDAYS):
        sent = outbound.get(weekday, 0)
        rate = round(inbound.get(weekday, 0) / sent * 100, 1) if sent else 0.0
        result.append({"day": label, "rate": rate})
    return result


# --------------------------------------------------------------------------
# Overview
# --------------------------------------------------------------------------
def overview(db: Session, user_id: str) -> dict:
    leads = _user_leads(db, user_id)
    campaigns = _user_campaigns(db, user_id)

    invites = sum(1 for l in leads if l.status in INVITED_STATES)
    connected = sum(1 for l in leads if l.status in CONNECTED_STATES)
    replied = sum(1 for l in leads if l.status in REPLIED_STATES)
    interested = sum(1 for l in leads if l.status == "interested")

    funnel = [
        {"stage": "Invites sent", "value": invites},
        {"stage": "Connected", "value": connected},
        {"stage": "Replied", "value": replied},
        {"stage": "Interested", "value": interested},
    ]

    campaign_perf = []
    for c in campaigns:
        stats = campaign_stats(c)
        sent = stats["invitesSent"]
        conn = stats["connected"]
        rep = stats["replied"]
        campaign_perf.append(
            {
                "campaignId": c.id,
                "name": c.name,
                "status": c.status,
                "sent": sent,
                "connected": conn,
                "replied": rep,
                "connectionRate": round(conn / sent * 100, 1) if sent else 0.0,
                "replyRate": round(rep / conn * 100, 1) if conn else 0.0,
            }
        )

    return {
        "series": build_series(db, user_id),
        "funnel": funnel,
        "campaigns": campaign_perf,
        "replyRateByDay": reply_rate_by_day(db, user_id),
    }


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------
def dashboard_stats(db: Session, user_id: str) -> dict:
    leads = _user_leads(db, user_id)
    campaigns = _user_campaigns(db, user_id)
    messages = _user_messages(db, user_id)

    total_leads = len(leads)
    # Leads imported as existing connections (source="connections") start as
    # status="connected" — Synex never sent them an invite request, so exclude
    # them from the "invitations sent" and "connected via Synex" counts.
    def _synex_invited(lead) -> bool:
        return (
            lead.status in INVITED_STATES
            and not (lead.source == "connections" and lead.status == "connected")
        )

    invitations_sent = sum(1 for l in leads if _synex_invited(l))
    connected = sum(
        1 for l in leads
        if l.status in CONNECTED_STATES
        and not (l.source == "connections" and l.status == "connected")
    )
    inbound = [m for m in messages if m.direction == "inbound"]
    replies_received = len(inbound)
    active = sum(1 for c in campaigns if c.status == "active")

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=30)
    prev_cutoff = now - timedelta(days=60)

    leads_recent = sum(1 for l in leads if (d := _aware(l.created_at)) and d >= cutoff)
    leads_prev = sum(
        1 for l in leads if (d := _aware(l.created_at)) and prev_cutoff <= d < cutoff
    )
    replies_recent = sum(1 for m in inbound if (d := _aware(m.sent_at)) and d >= cutoff)
    replies_prev = sum(
        1 for m in inbound if (d := _aware(m.sent_at)) and prev_cutoff <= d < cutoff
    )

    return {
        "totalLeads": total_leads,
        "totalLeadsDelta": _pct_change(leads_recent, leads_prev),
        "activeCampaigns": active,
        "invitationsSent": invitations_sent,
        # No per-event history is stored for invitations, so growth is not
        # measurable yet; report 0 rather than inventing a number.
        "invitationsSentDelta": 0.0,
        "repliesReceived": replies_received,
        "repliesReceivedDelta": _pct_change(replies_recent, replies_prev),
        "connectionRate": round(connected / invitations_sent * 100, 1) if invitations_sent else 0.0,
        "replyRate": round(replies_received / connected * 100, 1) if connected else 0.0,
    }


def activity_feed(db: Session, user_id: str) -> list[dict]:
    """Recent-activity feed built from real conversations and campaigns."""
    items: list[dict] = []
    now = datetime.now(timezone.utc)

    def _ts(dt: datetime | None) -> str:
        return (_aware(dt) or now).isoformat()

    convos = (
        db.query(models.Conversation)
        .filter(models.Conversation.user_id == user_id)
        .order_by(models.Conversation.last_message_at.desc())
        .limit(6)
        .all()
    )
    for c in convos:
        lead = c.lead
        name = f"{lead.first_name} {lead.last_name}".strip() if lead else "A lead"
        if c.status == "interested":
            items.append(
                {
                    "id": f"act_int_{c.id}",
                    "type": "marked_interested",
                    "title": "Marked interested",
                    "description": f"{name} is interested",
                    "timestamp": _ts(c.last_message_at),
                    "leadName": name,
                }
            )
        else:
            items.append(
                {
                    "id": f"act_reply_{c.id}",
                    "type": "reply_received",
                    "title": f"New reply from {name}",
                    "description": c.campaign.name if c.campaign else "Direct message",
                    "timestamp": _ts(c.last_message_at),
                    "leadName": name,
                }
            )

    for c in _user_campaigns(db, user_id):
        if c.status == "active":
            items.append(
                {
                    "id": f"act_camp_{c.id}",
                    "type": "campaign_started",
                    "title": "Campaign active",
                    "description": f"{c.name} is running",
                    "timestamp": _ts(c.updated_at),
                }
            )

    items.sort(key=lambda x: x["timestamp"], reverse=True)
    return items[:8]
