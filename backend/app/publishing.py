from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Literal
from pydantic import BaseModel, Field, field_validator
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
import httpx
from .database import get_db
from .deps import get_data_user, get_manager_user, get_current_user, get_admin_user
from .publishing_models import Post, Execution, WorkerHeartbeat, Preference
from .linkedin import owned, available, configured
from .sessions import aware
from .config import settings
from .assistant.config import assistant_config
from .deepgram_text import DeepgramTextError, complete

router = APIRouter(prefix="/publishing", tags=["publishing"])


def iso(value):
    return aware(value).isoformat() if value else None


def post_out(p):
    return {"id": p.id, "accountId": p.account_id, "title": p.title, "body": p.body,
            "status": p.status, "scheduledAt": iso(p.scheduled_at), "timezone": p.timezone,
            "version": p.version, "hasImage": bool(p.has_image), "attempts": p.attempts, "linkedinId": p.linkedin_id,
            "error": p.error, "updatedAt": iso(p.updated_at), "createdAt": iso(p.created_at)}


class DraftIn(BaseModel):
    title: str = Field(default="", max_length=160)
    body: str = Field(default="", max_length=3000)
    accountId: str | None = None
    version: int = Field(default=1, ge=1)


class ActionIn(BaseModel):
    action: Literal["schedule", "publish", "pause", "cancel", "draft"]
    scheduledAt: datetime | None = None
    timezone: str = "UTC"
    version: int = Field(ge=1)

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Choose a valid IANA time zone")
        return value


def get_post(db, user, post_id):
    p = db.get(Post, post_id)
    if not p or p.user_id != user.id:
        raise HTTPException(404, "Post not found")
    return p


def log(db, p, status, detail):
    db.add(Execution(user_id=p.user_id, post_id=p.id, status=status, detail=detail))


@router.get("/posts")
def posts(db: Session = Depends(get_db), user=Depends(get_data_user)):
    return [post_out(p) for p in db.query(Post).filter_by(user_id=user.id).order_by(Post.created_at.desc()).limit(1000)]


@router.post("/posts")
def create(payload: DraftIn, db: Session = Depends(get_db), user=Depends(get_manager_user)):
    if payload.accountId:
        owned(db, user, payload.accountId)
    p = Post(user_id=user.id, title=payload.title, body=payload.body, account_id=payload.accountId)
    db.add(p)
    db.flush()
    log(db, p, "draft", "Draft created")
    db.commit()
    return post_out(p)


@router.put("/posts/{post_id}")
def update(post_id: str, payload: DraftIn, db: Session = Depends(get_db), user=Depends(get_manager_user)):
    p = get_post(db, user, post_id)
    if payload.accountId:
        owned(db, user, payload.accountId)
    changed = db.query(Post).filter(Post.id == p.id, Post.version == payload.version, Post.status.in_(["draft", "paused", "failed", "cancelled"])).update({
        "title": payload.title, "body": payload.body, "account_id": payload.accountId,
        "version": Post.version + 1, "status": "draft", "error": None,
    }, synchronize_session=False)
    if not changed:
        db.rollback()
        raise HTTPException(409, "Post changed or cannot be edited. Pause scheduled content first, then reload.")
    log(db, p, "draft", "Draft updated")
    db.commit()
    db.refresh(p)
    return post_out(p)


@router.post("/posts/{post_id}/action")
def action(post_id: str, payload: ActionIn, db: Session = Depends(get_db), user=Depends(get_manager_user)):
    p = get_post(db, user, post_id)
    if p.version != payload.version or p.status in ("published", "publishing", "needs_review"):
        raise HTTPException(409, "This post cannot be changed. Reload to see its current status.")
    now = datetime.now(timezone.utc)
    target = {"pause": "paused", "cancel": "cancelled", "draft": "draft"}.get(payload.action, "scheduled")
    changes = {"status": target, "version": p.version + 1, "error": None}
    if target == "scheduled":
        if p.status not in ("draft", "paused", "failed", "cancelled", "scheduled", "retrying"):
            raise HTTPException(409, "Post is not eligible for scheduling")
        acc = owned(db, user, p.account_id)
        if not available(acc):
            raise HTTPException(409, "Connect a healthy LinkedIn account before publishing.")
        if "w_member_social" not in (acc.scopes or []):
            raise HTTPException(403, "Publishing requires LinkedIn Share on LinkedIn access (w_member_social). Reconnect after enabling this product.")
        if not p.body.strip():
            raise HTTPException(422, "Write your post before scheduling.")
        due = payload.scheduledAt
        if payload.action == "publish":
            due = now
        elif not due or due.tzinfo is None or due <= now:
            raise HTTPException(422, "Choose a future date with a time zone.")
        changes.update(scheduled_at=due.astimezone(timezone.utc), timezone=payload.timezone, attempts=0)
    count = db.query(Post).filter_by(id=p.id, version=payload.version, status=p.status).update(changes, synchronize_session=False)
    if not count:
        db.rollback()
        raise HTTPException(409, "Post changed. Reload and try again.")
    log(db, p, target, {"scheduled": "Publishing approved and queued", "paused": "Schedule paused", "cancelled": "Schedule cancelled", "draft": "Returned to draft"}[target])
    db.commit()
    db.refresh(p)
    return post_out(p)


@router.get("/activity")
def activity(db: Session = Depends(get_db), user=Depends(get_data_user)):
    return [{"id": e.id, "postId": e.post_id, "status": e.status, "detail": e.detail, "createdAt": iso(e.created_at)}
            for e in db.query(Execution).filter_by(user_id=user.id).order_by(Execution.created_at.desc()).limit(200)]


@router.get("/metrics")
def metrics(db: Session = Depends(get_db), user=Depends(get_data_user)):
    counts = dict(db.query(Post.status, func.count(Post.id)).filter_by(user_id=user.id).group_by(Post.status).all())
    total = counts.get("published", 0) + counts.get("failed", 0)
    return {"counts": counts, "successRate": round(counts.get("published", 0) / total * 100, 1) if total else None,
            "source": "SYNEX publishing records. Success rate counts published and failed posts only; unresolved deliveries are excluded."}


@router.get("/diagnostics")
def diagnostics(db: Session = Depends(get_db), user=Depends(get_admin_user)):
    last = db.query(func.max(WorkerHeartbeat.checked_at)).scalar()
    return {"oauthConfigured": configured(), "workerHealthy": bool(last and (datetime.now(timezone.utc) - aware(last)).total_seconds() < 120),
            "workerLastSeen": iso(last), "aiConfigured": bool(assistant_config.deepgram_api_key)}


class PrefIn(BaseModel):
    timezone: str


@router.get("/preferences")
def preferences(db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = db.get(Preference, user.id)
    return {"timezone": p.timezone if p else "UTC"}


@router.put("/preferences")
def update_preferences(payload: PrefIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    try:
        ZoneInfo(payload.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(422, "Choose a valid IANA time zone")
    p = db.get(Preference, user.id) or Preference(user_id=user.id)
    p.timezone = payload.timezone
    db.add(p)
    db.commit()
    return {"timezone": p.timezone}


class AssistIn(BaseModel):
    body: str = Field(min_length=1, max_length=3000)
    instruction: Literal["Improve clarity", "Make concise", "Suggest hashtags"]


@router.post("/assist")
def assist(payload: AssistIn, user=Depends(get_manager_user), db: Session = Depends(get_db)):
    if not assistant_config.deepgram_api_key:
        raise HTTPException(503, "Writing assistance is not configured.")
    db.rollback()  # the sign-in lookup is done: no transaction stays open while Deepgram is called
    try:
        body = complete(
            "Edit LinkedIn post drafts. Preserve factual meaning. Never invent claims. Return only the revised post, at most 3000 characters.",
            payload.instruction + "\n\n" + payload.body,
        )
        if not body.strip() or len(body) > 3000:
            raise ValueError()
        return {"body": body}
    except (DeepgramTextError, ValueError):
        raise HTTPException(502, "Writing assistance could not complete. Your draft has not changed.")
