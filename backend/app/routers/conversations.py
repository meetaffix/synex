from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..errors import sanitize_errors
from ..database import get_db
from ..deps import get_data_user
from ..serializers import conversation_out, message_out
from ..schemas import MessageIn, ConversationUpdateIn, ComposeMessageIn
from .. import engine, models

router = APIRouter(tags=["inbox"])


def _parse(model, body: dict):
    try:
        return model.model_validate(body)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=sanitize_errors(e.errors()))


def _owned(db: Session, user: models.User, convo_id: str) -> models.Conversation:
    c = db.get(models.Conversation, convo_id)
    if not c or c.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return c


def _sending_account(
    db: Session, user: models.User, preferred_id: str | None
) -> models.LinkedInAccount:
    """The account that should deliver a message: the conversation's own account when it is
    connected, otherwise any connected account this workspace owns."""
    account = db.get(models.LinkedInAccount, preferred_id) if preferred_id else None
    if account is None or account.user_id != user.id or not engine.account_is_live(account):
        account = next(
            (a for a in db.query(models.LinkedInAccount).filter_by(user_id=user.id).all() if engine.account_is_live(a)),
            None,
        )
    if account is None:
        raise HTTPException(
            status_code=400,
            detail="No sender account is connected, so the message cannot be delivered. "
            "Connect one under Sender accounts first.",
        )
    refusal = engine.manual_send_refusal(db, account, "send_message", datetime.now(timezone.utc))
    if refusal:
        raise HTTPException(status_code=409, detail=refusal)
    return account


def _queue_outbound(
    db: Session,
    convo: models.Conversation,
    account: models.LinkedInAccount,
    body: str,
) -> models.Message:
    """Record an outbound reply as queued and emit the send task. The message
    flips to sent/failed when the outreach worker reports the result."""
    now = datetime.now(timezone.utc)
    msg = models.Message(
        conversation_id=convo.id,
        direction="outbound",
        body=body,
        sent_at=now,
        read=True,
        delivery_status="queued",
    )
    db.add(msg)
    db.flush()  # assign msg.id so the task can reference it

    convo.last_message_preview = body
    convo.last_message_at = now
    convo.unread = False
    if convo.account_id is None:
        convo.account_id = account.id

    engine.emit_task(
        db, account, "send_message",
        {
            "messageId": msg.id,
            "leadId": convo.lead_id,
            "linkedinUrl": convo.lead.linkedin_url if convo.lead else "",
            "message": body,
            "manual": True,
        },
        f"reply:{msg.id}",
        priority=engine.MANUAL_PRIORITY,
    )
    db.commit()
    db.refresh(msg)
    return msg


def _delivery_meta(account: models.LinkedInAccount) -> dict:
    """Tell the UI whether the queued reply will go out now or wait."""
    live = engine.account_is_live(account, datetime.now(timezone.utc))
    return {
        "queued": True,
        "accountLive": live,
        "note": None
        if live
        else "Queued. It sends when the sender account is connected again.",
    }


@router.get("/conversations")
def read_conversations(
    conversationId: str | None = Query(None),
    status: str | None = Query(None),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_data_user),
):
    """Reads for the inbox: the conversation list (optionally filtered by
    ``status``/``search``), or — when ``conversationId`` is given — that
    thread's messages (which marks it read)."""
    if conversationId:
        return _messages(conversationId, db, user)
    convos = (
        db.query(models.Conversation)
        .filter(models.Conversation.user_id == user.id)
        .order_by(models.Conversation.last_message_at.desc())
        .all()
    )
    result = [conversation_out(c) for c in convos]

    if status and status != "all":
        result = [c for c in result if c["status"] == status]
    if search:
        s = search.lower()
        result = [
            c
            for c in result
            if s in (c["leadName"] or "").lower()
            or s in (c["leadCompany"] or "").lower()
        ]
    return result


def _messages(convo_id: str, db: Session, user: models.User):
    convo = _owned(db, user, convo_id)
    # Reading a thread marks it as read.
    if convo.unread:
        convo.unread = False
        db.commit()
    msgs = sorted(convo.messages, key=lambda m: m.sent_at or datetime.min)
    return [message_out(m) for m in msgs]


def _reply(convo_id: str, payload: MessageIn, db: Session, user: models.User):
    """Record the reply and queue it for the outreach worker to send on LinkedIn."""
    convo = _owned(db, user, convo_id)
    account = _sending_account(db, user, convo.account_id)
    msg = _queue_outbound(db, convo, account, payload.body)
    return {**message_out(msg), "delivery": _delivery_meta(account)}


def _compose(payload: ComposeMessageIn, db: Session, user: models.User):
    """Start a brand-new conversation with a lead from the unibox (rather than
    only replying to a synced thread). Reuses an existing conversation with the
    same lead when one already exists, so we never create a duplicate thread."""
    lead = db.get(models.Lead, payload.lead_id)
    if not lead or lead.user_id != user.id:
        raise HTTPException(status_code=404, detail="Lead not found")
    if not (lead.linkedin_url or "").strip():
        raise HTTPException(
            status_code=400,
            detail="This lead has no LinkedIn URL, so a message cannot be delivered.",
        )

    account = _sending_account(db, user, None)

    convo = (
        db.query(models.Conversation)
        .filter(
            models.Conversation.user_id == user.id,
            models.Conversation.lead_id == lead.id,
        )
        .first()
    )
    if convo is None:
        convo = models.Conversation(
            user_id=user.id,
            lead_id=lead.id,
            account_id=account.id,
            status="active",
        )
        db.add(convo)
        db.flush()

    msg = _queue_outbound(db, convo, account, payload.body)
    return {
        "conversation": conversation_out(convo),
        "message": message_out(msg),
        "delivery": _delivery_meta(account),
    }


def _update(convo_id: str, payload: ConversationUpdateIn, db: Session, user: models.User):
    convo = _owned(db, user, convo_id)
    data = payload.model_dump(exclude_unset=True)
    if "status" in data and data["status"] is not None:
        convo.status = data["status"]
    if "unread" in data and data["unread"] is not None:
        convo.unread = data["unread"]
    db.commit()
    db.refresh(convo)
    return conversation_out(convo)


@router.post("/conversations")
def write_conversations(
    body: dict,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_data_user),
):
    """Write gateway for the inbox:

    * ``compose`` — start/continue a thread with a lead: ``leadId`` + ``body``
    * ``reply``   — reply in a thread: ``conversationId`` + ``body``
    * ``update``  — change a thread: ``conversationId`` + ``status``/``unread``
    """
    action = body.get("action")
    if action == "compose":
        return _compose(_parse(ComposeMessageIn, body), db, user)
    if action == "reply":
        if not body.get("conversationId"):
            raise HTTPException(status_code=400, detail="conversationId is required to reply")
        return _reply(body["conversationId"], _parse(MessageIn, body), db, user)
    if action == "update":
        if not body.get("conversationId"):
            raise HTTPException(status_code=400, detail="conversationId is required")
        return _update(body["conversationId"], _parse(ConversationUpdateIn, body), db, user)
    raise HTTPException(status_code=400, detail=f"Unknown conversation action: {action!r}")
