"""Manual engagement: react to a LinkedIn post or comment on it from one of your sender accounts, by hand. The worker does it within that account's
limits (its own hard ceiling), and the history says what happened. The comment is your own words; Synex never writes it while sending."""
import re
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import engine, models
from ..database import get_db
from ..deps import get_data_user, get_manager_user

router = APIRouter(prefix="/engagement", tags=["engagement"])
REACTIONS = {"like": "Like", "celebrate": "Celebrate", "support": "Support", "love": "Love", "insightful": "Insightful", "funny": "Funny"}
POST_PATH = re.compile(r"^/(feed/update/urn:li:(activity|ugcPost|share):\d+|posts/[^\s?/]+)/?$", re.I)
HOSTS = {"www.linkedin.com", "linkedin.com"}
MAX_COMMENT = 1250


class EngageIn(BaseModel):
    account_id: str = Field(alias="accountId")
    post_url: str = Field(alias="postUrl", max_length=500)
    reaction: Literal["like", "celebrate", "support", "love", "insightful", "funny"] | None = None
    comment: str | None = Field(None, max_length=MAX_COMMENT)

    model_config = {"populate_by_name": True}


def _out(row: models.Engagement, names: dict[str, str]) -> dict:
    return {"id": row.id, "accountId": row.account_id, "account": names.get(row.account_id, "A removed account"), "postUrl": row.post_url, "reaction": row.reaction,
            "comment": row.comment, "status": row.status, "detail": row.detail, "createdAt": row.created_at.isoformat(), "doneAt": row.done_at.isoformat() if row.done_at else None}


def check_post_url(url: str) -> str:
    parts = urlsplit((url or "").strip())
    if parts.scheme not in ("http", "https") or parts.hostname not in HOSTS or not POST_PATH.match(parts.path):
        raise HTTPException(422, "Paste the address of one LinkedIn post (it contains linkedin.com/feed/update/ or linkedin.com/posts/).")
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


@router.post("", status_code=201)
def engage(body: EngageIn, db: Session = Depends(get_db), user: models.User = Depends(get_manager_user)):
    if not body.reaction and not (body.comment or "").strip():
        raise HTTPException(422, "Choose a reaction, write a comment, or both.")
    url = check_post_url(body.post_url)
    account = db.get(models.LinkedInAccount, body.account_id)
    if account is None or account.user_id != user.id:
        raise HTTPException(404, "Sender account not found")
    if not engine.account_is_live(account):
        raise HTTPException(409, "This sender is paused or not connected. Reconnect or resume it first.")
    refusal = engine.manual_send_refusal(db, account, "engage_post", datetime.now(timezone.utc))
    if refusal:
        raise HTTPException(409, refusal.replace("messages today", "reactions and comments today"))
    row = models.Engagement(user_id=user.id, account_id=account.id, post_url=url, reaction=body.reaction, comment=(body.comment or "").strip() or None)
    db.add(row)
    db.flush()
    payload = {"linkedinUrl": url, "reaction": REACTIONS.get(body.reaction or ""), "comment": row.comment, "engagementId": row.id}
    task = engine.emit_task(db, account, "engage_post", payload, f"engage:{row.id}")
    if task is None:
        db.rollback()
        raise HTTPException(409, "This sender has no room left today for reactions and comments.")
    row.task_id = task.id
    db.commit()
    return _out(row, {account.id: account.name})


@router.get("")
def history(account_id: str | None = Query(None, alias="accountId"), limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db),
            user: models.User = Depends(get_data_user)):
    query = db.query(models.Engagement).filter_by(user_id=user.id)
    if account_id:
        query = query.filter_by(account_id=account_id)
    names = {a.id: a.name for a in db.query(models.LinkedInAccount).filter_by(user_id=user.id)}
    return {"items": [_out(r, names) for r in query.order_by(models.Engagement.created_at.desc()).limit(limit)], "reactions": list(REACTIONS), "maxComment": MAX_COMMENT}


@router.delete("/{engagement_id}", status_code=204)
def cancel(engagement_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_manager_user)):
    """Cancel one that has not run yet. One that is done stays in the history."""
    row = db.get(models.Engagement, engagement_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "Not found")
    task = db.get(models.AgentTask, row.task_id) if row.task_id else None
    if row.status != "queued" or (task is not None and task.status != "pending"):
        raise HTTPException(409, "This one has already started or finished, so it cannot be cancelled.")
    if task is not None:
        task.status = "cancelled"
    row.status, row.detail = "cancelled", "Cancelled by you."
    db.commit()
    return Response(status_code=204)
