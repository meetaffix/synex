"""One safety score per sender account, with plain advice. Competitors show raw limits; this says whether the account is safe and what to do.

The score starts at 100 and loses points for what LinkedIn watches: a low acceptance rate, failed actions, a session problem,
running at the top of the daily limit, and a young account sending a lot. Everything is read from Synex's own records.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from . import engine, models

ACCEPTED = engine.ACCEPTED_STATES


def _sent_invites(db: Session, account: models.LinkedInAccount, since: datetime) -> list[models.AgentTask]:
    return (db.query(models.AgentTask)
            .filter(models.AgentTask.account_id == account.id, models.AgentTask.type == "send_invite",
                    models.AgentTask.status == "done", models.AgentTask.created_at >= since).all())


def score(db: Session, account: models.LinkedInAccount, now: datetime) -> dict:
    """{score 0-100, level good|watch|risk, label, acceptanceRate, advice[]} for one account."""
    points, advice = 100, []

    session = (account.session_status or "").lower()
    if session == "restricted" or account.status == "restricted":
        points -= 70
        advice.append("LinkedIn restricted this account. Stop all campaigns on it and sign in on LinkedIn to resolve it.")
    elif session in ("needs_reconnect", "disconnected"):
        points -= 30
        advice.append("The account is not connected. Reconnect it so campaigns can continue.")

    since = now - timedelta(days=30)
    invites = _sent_invites(db, account, since)
    rate = None
    if invites:
        lead_ids = {(t.payload or {}).get("leadId") for t in invites} - {None}
        accepted = db.query(models.Lead).filter(models.Lead.id.in_(lead_ids), models.Lead.status.in_(ACCEPTED)).count() if lead_ids else 0
        rate = round(accepted / len(invites) * 100)
        if len(invites) >= 10 and rate < 20:
            points -= 30
            advice.append(f"Only {rate}% of connection requests were accepted in 30 days. LinkedIn notices this: target closer matches and send fewer requests.")
        elif len(invites) >= 10 and rate < 30:
            points -= 15
            advice.append(f"{rate}% of requests were accepted. Above 30% is healthy: personalise the request or narrow the list.")

    week = now - timedelta(days=7)
    recent = db.query(models.AgentTask).filter(models.AgentTask.account_id == account.id, models.AgentTask.created_at >= week,
                                               models.AgentTask.status.in_(["done", "failed", "needs_review"])).all()
    failed = sum(t.status != "done" for t in recent)
    if len(recent) >= 5 and failed / len(recent) > 0.2:
        points -= 20
        advice.append(f"{failed} of {len(recent)} actions failed this week. Check the account's activity for the reason before sending more.")

    limit = engine.effective_daily_limit(account, now)
    used = limit - engine.remaining_capacity(account, now)
    if limit > 0 and used / limit >= 0.9:
        points -= 10
        advice.append("The account is at its daily limit. That is allowed, but a little below the limit looks more natural.")

    started = engine._aware(account.warmup_started_at) or engine._aware(account.created_at)
    age_days = (now - started).days if started else 0
    if age_days < 14 and limit > 25:
        points -= 15
        advice.append(f"The account started on Synex {age_days} days ago. Keep the daily limit low for its first two weeks.")

    points = max(0, min(100, points))
    level = "good" if points >= 75 else "watch" if points >= 50 else "risk"
    if not advice:
        advice.append("Nothing to change: the account is behaving like a careful person.")
    return {"score": points, "level": level, "label": {"good": "Healthy", "watch": "Watch", "risk": "At risk"}[level],
            "acceptanceRate": rate, "advice": advice}
