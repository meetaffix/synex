"""The unified inbox: every filter, tags, interest labels, bulk actions, drafts, scheduled messages, AI suggested replies, CSV export and a gentle refresh.

Reading a conversation never counts against outreach limits. Sending a reply is checked against the sender's limits at the moment it would go out,
and a scheduled message is checked again when its time comes.
"""
import csv
import io
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from .. import ai_prompt, engine, integrations_core as integrations, models, providers
from ..database import get_db
from ..deps import get_data_user, get_manager_user
from ..serializers import message_out

router = APIRouter(prefix="/inbox", tags=["inbox"])
INTERESTS = ("interested", "not_interested", "meeting_booked", "wrong_person", "follow_up_later")
INTEREST_LABEL = {"interested": "Interested", "not_interested": "Not interested", "meeting_booked": "Meeting booked", "wrong_person": "Wrong person", "follow_up_later": "Follow up later"}
MAX_TAG = 40
MAX_TAGS = 10


class Filters(BaseModel):
    q: str = ""
    needs_reply: bool = False
    i_messaged_last: bool = False
    unread: bool = False
    starred: bool = False
    drafts: bool = False
    scheduled: bool = False
    archived: bool = False
    tag: str = ""
    interest: str = ""
    accounts: list[str] = Field(default_factory=list)
    campaigns: list[str] = Field(default_factory=list)
    campaign_mode: Literal["include", "exclude"] = "include"
    where: Literal["", "messages_sent", "responses"] = ""
    date_from: datetime | None = None
    date_to: datetime | None = None


def filters(q: str = "", needs_reply: bool = False, i_messaged_last: bool = False, unread: bool = False, starred: bool = False, drafts: bool = False,
            scheduled: bool = False, archived: bool = False, tag: str = "", interest: str = "", accounts: str = "", campaigns: str = "",
            campaign_mode: str = "include", where: str = "", date_from: datetime | None = None, date_to: datetime | None = None) -> Filters:
    try:
        return Filters(q=q, needs_reply=needs_reply, i_messaged_last=i_messaged_last, unread=unread, starred=starred, drafts=drafts, scheduled=scheduled,
                       archived=archived, tag=tag, interest=interest, accounts=[a for a in accounts.split(",") if a], campaigns=[c for c in campaigns.split(",") if c],
                       campaign_mode=campaign_mode, where=where, date_from=date_from, date_to=date_to)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


def _last_direction():
    return (select(models.Message.direction).where(models.Message.conversation_id == models.Conversation.id)
            .order_by(models.Message.sent_at.desc()).limit(1).correlate(models.Conversation).scalar_subquery())


def build_query(db: Session, user: models.User, f: Filters):
    C, M = models.Conversation, models.Message
    query = db.query(C).join(models.Lead, models.Lead.id == C.lead_id).filter(C.user_id == user.id)
    query = query.filter(C.status == "archived") if f.archived else query.filter(C.status != "archived")
    if f.q.strip():
        like = f"%{f.q.strip().lower()}%"
        in_message = exists().where(and_(M.conversation_id == C.id, func.lower(M.body).like(like)))
        query = query.filter(or_(func.lower(models.Lead.first_name + " " + models.Lead.last_name).like(like), func.lower(models.Lead.company).like(like),
                                 func.lower(models.Lead.job_title).like(like), in_message))
    if f.needs_reply:
        query = query.filter(_last_direction() == "inbound", C.answered.is_(False))
    if f.i_messaged_last:
        query = query.filter(_last_direction() == "outbound")
    if f.unread:
        query = query.filter(C.unread.is_(True))
    if f.starred:
        query = query.filter(C.starred.is_(True))
    if f.drafts:
        query = query.filter(C.draft_body.isnot(None), C.draft_body != "")
    if f.scheduled:
        query = query.filter(exists().where(and_(models.ScheduledMessage.conversation_id == C.id, models.ScheduledMessage.status == "pending")))
    if f.interest:
        query = query.filter(C.interest == f.interest)
    if f.accounts:
        query = query.filter(C.account_id.in_(f.accounts))
    if f.campaigns:
        listed = C.campaign_id.in_(f.campaigns)
        query = query.filter(listed if f.campaign_mode == "include" else or_(C.campaign_id.is_(None), ~listed))
    if f.where == "messages_sent":
        query = query.filter(C.campaign_id.isnot(None), exists().where(and_(M.conversation_id == C.id, M.direction == "outbound")))
    elif f.where == "responses":
        query = query.filter(exists().where(and_(M.conversation_id == C.id, M.direction == "inbound")))
    if f.date_from:
        query = query.filter(C.last_message_at >= f.date_from)
    if f.date_to:
        query = query.filter(C.last_message_at <= f.date_to)
    return query


def _out(c: models.Conversation, direction: str | None, scheduled: int, accounts: dict) -> dict:
    lead = c.lead
    name = f"{lead.first_name} {lead.last_name}".strip() if lead else ""
    return {
        "id": c.id, "leadId": c.lead_id, "leadName": name or "Unknown", "leadTitle": (lead.job_title or lead.headline or "") if lead else "",
        "leadCompany": lead.company if lead else "", "linkedinUrl": lead.linkedin_url if lead else None, "avatarUrl": lead.avatar_url if lead else None,
        "accountId": c.account_id, "accountName": accounts.get(c.account_id), "campaignId": c.campaign_id,
        "campaignName": c.campaign.name if c.campaign else None, "lastMessagePreview": c.last_message_preview, "lastMessageAt": c.last_message_at.isoformat() if c.last_message_at else None,
        "unread": bool(c.unread), "status": c.status, "starred": bool(c.starred), "answered": bool(c.answered), "tags": c.tags or [], "interest": c.interest,
        "hasDraft": bool((c.draft_body or "").strip()), "draftBody": c.draft_body or "", "scheduledCount": scheduled, "lastDirection": direction,
        "needsReply": direction == "inbound" and not c.answered,
    }


def _page(db: Session, user: models.User, f: Filters, limit: int, offset: int):
    query = build_query(db, user, f)
    query = query.order_by(models.Conversation.last_message_at.desc(), models.Conversation.id)
    rows = query.all() if f.tag else None
    if rows is not None:
        rows = [c for c in rows if f.tag in (c.tags or [])]
        total, page = len(rows), rows[offset:offset + limit]
    else:
        total, page = query.count(), query.offset(offset).limit(limit).all()
    ids = [c.id for c in page]
    last = {}
    if ids:
        for cid, direction in db.query(models.Message.conversation_id, models.Message.direction).filter(models.Message.conversation_id.in_(ids)).order_by(models.Message.sent_at.asc()):
            last[cid] = direction
    pending = dict(db.query(models.ScheduledMessage.conversation_id, func.count()).filter(models.ScheduledMessage.conversation_id.in_(ids), models.ScheduledMessage.status == "pending")
                   .group_by(models.ScheduledMessage.conversation_id).all()) if ids else {}
    names = dict(db.query(models.LinkedInAccount.id, models.LinkedInAccount.name).filter_by(user_id=user.id).all())
    return total, [_out(c, last.get(c.id), pending.get(c.id, 0), names) for c in page]


@router.get("/conversations")
def conversations(f: Filters = Depends(filters), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), db: Session = Depends(get_db),
                  user: models.User = Depends(get_data_user)):
    total, items = _page(db, user, f, limit, offset)
    return {"items": items, "total": total}


@router.get("/meta")
def meta(db: Session = Depends(get_db), user: models.User = Depends(get_data_user)):
    """What the filters offer: this workspace's senders (with when each was last read), campaigns and tags."""
    accounts = db.query(models.LinkedInAccount).filter(models.LinkedInAccount.user_id == user.id, models.LinkedInAccount.status != "deleted").all()
    campaigns = db.query(models.Campaign).filter_by(user_id=user.id).order_by(models.Campaign.name).all()
    tags = sorted({t for (row,) in db.query(models.Conversation.tags).filter_by(user_id=user.id) for t in (row or [])})
    def last_skipped(a: models.LinkedInAccount) -> int:
        task = (db.query(models.AgentTask).filter(models.AgentTask.account_id == a.id, models.AgentTask.type == "sync_inbox", models.AgentTask.status == "done")
                .order_by(models.AgentTask.updated_at.desc()).first())
        return int((task.result or {}).get("skipped", 0)) if task else 0
    return {"accounts": [{"id": a.id, "name": a.name, "lastSyncedAt": a.last_inbox_sync_at.isoformat() if a.last_inbox_sync_at else None, "live": engine.account_is_live(a),
                          "syncMode": a.sync_mode or "synex_only", "lastSkipped": last_skipped(a)} for a in accounts],
            "campaigns": [{"id": c.id, "name": c.name} for c in campaigns], "tags": tags,
            "interests": [{"id": k, "label": v} for k, v in INTEREST_LABEL.items()]}


Action = Literal["read", "unread", "star", "unstar", "archive", "unarchive", "answered", "unanswered", "tag_add", "tag_remove", "interest"]


class BulkIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=500)
    action: Action
    value: str | None = None


def _clean_tag(value: str | None) -> str:
    tag = (value or "").strip()
    if not tag or len(tag) > MAX_TAG:
        raise HTTPException(422, f"A tag is 1 to {MAX_TAG} characters.")
    return tag


@router.post("/bulk")
def bulk(body: BulkIn, db: Session = Depends(get_db), user: models.User = Depends(get_manager_user)):
    rows = db.query(models.Conversation).filter(models.Conversation.user_id == user.id, models.Conversation.id.in_(body.ids)).all()
    if body.action == "interest" and body.value not in (*INTERESTS, "", None):
        raise HTTPException(422, "Choose one of: " + ", ".join(INTERESTS) + ", or none.")
    tag = _clean_tag(body.value) if body.action in ("tag_add", "tag_remove") else None
    for c in rows:
        if body.action == "read":
            c.unread = False
        elif body.action == "unread":
            c.unread = True
        elif body.action == "star":
            c.starred = True
        elif body.action == "unstar":
            c.starred = False
        elif body.action == "archive":
            c.status = "archived"
        elif body.action == "unarchive":
            c.status = "active"
        elif body.action == "answered":
            c.answered, c.unread = True, False
        elif body.action == "unanswered":
            c.answered = False
        elif body.action == "tag_add":
            current = list(c.tags or [])
            if tag not in current:
                if len(current) >= MAX_TAGS:
                    raise HTTPException(422, f"A conversation can have at most {MAX_TAGS} tags.")
                c.tags = [*current, tag]
        elif body.action == "tag_remove":
            c.tags = [t for t in (c.tags or []) if t != tag]
        elif body.action == "interest":
            if body.value == "interested" and c.interest != "interested":
                integrations.emit(db, user.id, "lead_interested", {"name": c.lead.first_name if c.lead else "", "lead": c.lead.first_name if c.lead else ""})
            c.interest = body.value or None
    db.commit()
    return {"changed": len(rows)}


@router.get("/export")
def export(f: Filters = Depends(filters), db: Session = Depends(get_db), user: models.User = Depends(get_data_user)):
    """The conversations the current filters show, as CSV (up to 5,000)."""
    _, items = _page(db, user, f, 5000, 0)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["name", "company", "linkedin_url", "account", "campaign", "last_message_at", "last_message", "unread", "starred", "interest", "tags"])
    safe = lambda v: "'" + v if v[:1] in ("=", "+", "-", "@") else v  # noqa: E731 - stop spreadsheets running a pasted formula
    for c in items:
        writer.writerow([safe(c["leadName"]), safe(c["leadCompany"] or ""), safe(c["linkedinUrl"] or ""), safe(c["accountName"] or ""), safe(c["campaignName"] or ""),
                         c["lastMessageAt"] or "", safe((c["lastMessagePreview"] or "").replace("\n", " ")), c["unread"], c["starred"], c["interest"] or "", safe(";".join(c["tags"]))])
    return Response(out.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="synex-inbox.csv"'})


# ---- drafts, scheduled messages -----------------------------------------------------------------------------------

def _owned(db: Session, user: models.User, convo_id: str) -> models.Conversation:
    c = db.get(models.Conversation, convo_id)
    if c is None or c.user_id != user.id:
        raise HTTPException(404, "Conversation not found")
    return c


class DraftIn(BaseModel):
    body: str = Field(max_length=3000)


@router.put("/{convo_id}/draft")
def save_draft(convo_id: str, body: DraftIn, db: Session = Depends(get_db), user: models.User = Depends(get_manager_user)):
    c = _owned(db, user, convo_id)
    c.draft_body = body.body.strip() or None
    db.commit()
    return {"draft": c.draft_body or ""}


class ScheduleIn(BaseModel):
    body: str = Field(min_length=1, max_length=3000)
    send_at: datetime = Field(alias="sendAt")
    model_config = {"populate_by_name": True}


@router.post("/{convo_id}/schedule", status_code=201)
def schedule(convo_id: str, body: ScheduleIn, db: Session = Depends(get_db), user: models.User = Depends(get_manager_user)):
    c = _owned(db, user, convo_id)
    when = body.send_at if body.send_at.tzinfo else body.send_at.replace(tzinfo=timezone.utc)
    if when <= datetime.now(timezone.utc):
        raise HTTPException(422, "Pick a time in the future.")
    account = db.get(models.LinkedInAccount, c.account_id) if c.account_id else None
    if account is None or account.user_id != user.id:
        raise HTTPException(409, "This conversation has no sender account to send from.")
    item = models.ScheduledMessage(user_id=user.id, conversation_id=c.id, account_id=account.id, body=body.body.strip(), send_at=when, status="pending")
    db.add(item)
    c.draft_body = None
    db.commit()
    return _scheduled_out(item)


def _scheduled_out(s: models.ScheduledMessage) -> dict:
    return {"id": s.id, "conversationId": s.conversation_id, "body": s.body, "sendAt": s.send_at.isoformat(), "status": s.status, "error": s.error}


@router.get("/{convo_id}/scheduled")
def scheduled(convo_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_data_user)):
    c = _owned(db, user, convo_id)
    rows = db.query(models.ScheduledMessage).filter_by(conversation_id=c.id).order_by(models.ScheduledMessage.send_at).all()
    return [_scheduled_out(r) for r in rows]


@router.delete("/scheduled/{scheduled_id}", status_code=204)
def cancel_scheduled(scheduled_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_manager_user)):
    item = db.get(models.ScheduledMessage, scheduled_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(404, "Scheduled message not found")
    if item.status == "pending":
        item.status = "cancelled"
        db.commit()
    return Response(status_code=204)


def release_due(db: Session, now: datetime) -> int:
    """Send scheduled messages whose time has come. Each is checked against the sender's limits now: one that cannot go out is marked failed with the reason."""
    from .conversations import _queue_outbound
    sent = 0
    for item in db.query(models.ScheduledMessage).filter(models.ScheduledMessage.status == "pending", models.ScheduledMessage.send_at <= now).all():
        convo, account = db.get(models.Conversation, item.conversation_id), db.get(models.LinkedInAccount, item.account_id)
        reason = None
        if convo is None or account is None:
            reason = "The conversation or its sender no longer exists."
        elif not engine.account_is_live(account, now):
            reason = "The sender account was not connected at the scheduled time."
        else:
            reason = engine.manual_send_refusal(db, account, "send_message", now)
        if reason:
            item.status, item.error = "failed", reason
            continue
        _queue_outbound(db, convo, account, item.body)
        item.status = "sent"
        sent += 1
    db.commit()
    return sent


# ---- AI suggested reply ----------------------------------------------------------------------------------------------

@router.get("/suggest-cost")
def suggest_cost(user: models.User = Depends(get_data_user)):
    """What one suggested reply costs, shown before it is written."""
    from ..config import DEEPGRAM_USD_PER_MINUTE, DRAFT_SECONDS_ESTIMATE
    name = providers.provider_name()
    usd = round(DRAFT_SECONDS_ESTIMATE / 60 * DEEPGRAM_USD_PER_MINUTE, 4) if name == "deepgram" else 0.0
    return {"provider": name, "estimatedUsd": usd}


@router.post("/{convo_id}/suggest-reply")
def suggest_reply(convo_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_manager_user)):
    """A suggested reply written from the thread and the campaign's AI context. It is saved as the conversation's draft: nothing is sent."""
    c = _owned(db, user, convo_id)
    thread = [(m.direction, m.body) for m in sorted(c.messages, key=lambda m: m.sent_at or datetime.min)][-8:]
    if not any(d == "inbound" for d, _ in thread):
        raise HTTPException(409, "There is nothing to reply to yet: the person has not written.")
    lead = c.lead
    fields = {"first_name": lead.first_name if lead else "", "last_name": lead.last_name if lead else "", "company": lead.company if lead else "",
              "job_title": lead.job_title if lead else "", "headline": lead.headline if lead else ""}
    context = dict(c.campaign.ai_context or {}) if c.campaign else {}
    system, prompt = ai_prompt.build_prompt("reply", fields, {"tone": "auto", "strategy": "auto"}, context)
    prompt += "\nThe conversation so far (oldest first):\n" + "\n".join(f"{'Prospect' if d == 'inbound' else 'Sender'}: {t[:600]}" for d, t in thread)
    prompt += "\nWrite the sender's next reply."
    db.rollback()  # nothing stays open while the provider is called
    provider = providers.get_ai_provider()
    source = "template"
    try:
        if isinstance(provider, (providers.DeepgramAIProvider, providers.OllamaAIProvider)):
            text = provider.generate_message("reply", "friendly", fields, {"config": {"tone": "auto", "strategy": "auto", "instructions": "Reply to the prospect's last message: " + thread[-1][1][:300]}, "context": context})
            source = providers.provider_name()
        else:
            text = providers.TemplateAIProvider().generate_message("message", "friendly", fields)
    except Exception:  # noqa: BLE001 - the service was unreachable or refused: the template is still a usable starting point
        text = providers.TemplateAIProvider().generate_message("message", "friendly", fields)
    text = providers.render_variables(text, lead) if lead else text
    c = _owned(db, user, convo_id)
    c.draft_body = text[:3000]
    db.commit()
    return {"text": c.draft_body, "source": source, "provider": providers.provider_name()}


# ---- refresh -------------------------------------------------------------------------------------------------------------

class RefreshIn(BaseModel):
    account_ids: list[str] = Field(default_factory=list, alias="accountIds")
    model_config = {"populate_by_name": True}


@router.post("/refresh", status_code=202)
def refresh(body: RefreshIn, db: Session = Depends(get_db), user: models.User = Depends(get_manager_user)):
    """Ask for the senders' inboxes to be read now. Each read is one paced task under the inbox ceiling, never the outreach limits."""
    accounts = db.query(models.LinkedInAccount).filter(models.LinkedInAccount.user_id == user.id, models.LinkedInAccount.status != "deleted").all()
    if body.account_ids:
        accounts = [a for a in accounts if a.id in body.account_ids]
    now = datetime.now(timezone.utc)
    queued, skipped = 0, []
    for a in accounts:
        if not engine.account_is_live(a, now):
            skipped.append({"account": a.name, "reason": "not connected"})
            continue
        recent = db.query(models.AgentTask.id).filter(models.AgentTask.account_id == a.id, models.AgentTask.type == "sync_inbox",
                                                      models.AgentTask.status.in_(["pending", "running"])).first()
        if recent:
            skipped.append({"account": a.name, "reason": "already reading"})
            continue
        task = engine.emit_task(db, a, "sync_inbox", {"accountId": a.id}, f"inbox-refresh:{a.id}:{now.isoformat()}")
        if task is None:
            skipped.append({"account": a.name, "reason": "today's inbox reading limit is used up"})
        else:
            queued += 1
    db.commit()
    return {"queued": queued, "skipped": skipped}
