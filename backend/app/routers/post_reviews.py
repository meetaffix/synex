"""Post review: the owner invites a named reviewer with a private link; the reviewer reads the post and leaves a comment, an approval or a request for
changes, without an account. The link is shown once, only its hash is kept, it expires after 14 days and can be revoked. An approval is recorded, never
acted on: the owner still publishes."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import integrations_core as core
from ..database import get_db
from ..deps import get_data_user, get_manager_user
from ..publishing_models import Post, ReviewFeedback, ReviewLink
from ..sessions import aware

router = APIRouter(tags=["post reviews"])
LINK_DAYS = 14


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _owned_post(db: Session, user, post_id: str) -> Post:
    post = db.get(Post, post_id)
    if post is None or post.user_id != user.id:
        raise HTTPException(404, "Post not found")
    return post


def _feedback_out(f: ReviewFeedback) -> dict:
    return {"id": f.id, "author": f.author, "decision": f.decision, "body": f.body, "postVersion": f.post_version, "createdAt": aware(f.created_at).isoformat(),
            "fromReviewer": f.link_id is not None}


def _link_out(link: ReviewLink) -> dict:
    now = _now()
    state = "revoked" if link.revoked_at else "expired" if aware(link.expires_at) <= now else "active"
    return {"id": link.id, "reviewer": link.reviewer, "state": state, "expiresAt": aware(link.expires_at).isoformat(),
            "lastSeenAt": aware(link.last_seen_at).isoformat() if link.last_seen_at else None, "createdAt": aware(link.created_at).isoformat()}


class ReviewerIn(BaseModel):
    reviewer: str = Field(min_length=1, max_length=80)


class FeedbackIn(BaseModel):
    body: str = Field(default="", max_length=2000)
    decision: Literal["comment", "approve", "changes"] = "comment"


@router.get("/publishing/posts/{post_id}/reviews")
def reviews(post_id: str, db: Session = Depends(get_db), user=Depends(get_data_user)):
    post = _owned_post(db, user, post_id)
    links = db.query(ReviewLink).filter_by(post_id=post.id).order_by(ReviewLink.created_at).all()
    thread = db.query(ReviewFeedback).filter_by(post_id=post.id).order_by(ReviewFeedback.created_at).all()
    approvals = sorted({f.author for f in thread if f.decision == "approve" and f.post_version == post.version})
    return {"links": [_link_out(l) for l in links], "thread": [_feedback_out(f) for f in thread], "approvedBy": approvals}


@router.post("/publishing/posts/{post_id}/reviewers", status_code=201)
def invite(post_id: str, body: ReviewerIn, db: Session = Depends(get_db), user=Depends(get_manager_user)):
    post = _owned_post(db, user, post_id)
    if db.query(ReviewLink).filter_by(post_id=post.id, revoked_at=None).count() >= 10:
        raise HTTPException(409, "A post can have up to 10 reviewers. Revoke one first.")
    token = secrets.token_urlsafe(32)
    link = ReviewLink(post_id=post.id, user_id=user.id, reviewer=body.reviewer.strip(), token_hash=_hash(token), expires_at=_now() + timedelta(days=LINK_DAYS))
    db.add(link)
    db.commit()
    return {**_link_out(link), "token": token, "path": f"/review/{token}", "note": "Copy this link now. It is shown only once and works for 14 days."}


@router.delete("/publishing/posts/{post_id}/reviewers/{link_id}", status_code=204)
def revoke(post_id: str, link_id: str, db: Session = Depends(get_db), user=Depends(get_manager_user)):
    post = _owned_post(db, user, post_id)
    link = db.get(ReviewLink, link_id)
    if link is None or link.post_id != post.id:
        raise HTTPException(404, "Reviewer not found")
    link.revoked_at = _now()
    db.commit()
    return Response(status_code=204)


@router.post("/publishing/posts/{post_id}/feedback", status_code=201)
def owner_reply(post_id: str, body: FeedbackIn, db: Session = Depends(get_db), user=Depends(get_manager_user)):
    post = _owned_post(db, user, post_id)
    if not body.body.strip():
        raise HTTPException(422, "Write a reply first.")
    reply = ReviewFeedback(post_id=post.id, author=user.full_name or "Owner", decision="comment", body=body.body.strip(), post_version=post.version)
    db.add(reply)
    db.commit()
    return _feedback_out(reply)


# ---- the reviewer's side: no account, only the link ----------------------------------------------------------------------

def _link(db: Session, token: str) -> tuple[ReviewLink, Post]:
    link = db.query(ReviewLink).filter_by(token_hash=_hash(token)).first()
    if link is None or link.revoked_at is not None or aware(link.expires_at) <= _now():
        raise HTTPException(404, "This review link is not valid any more. Ask the person who sent it for a new one.")
    post = db.get(Post, link.post_id)
    if post is None:
        raise HTTPException(404, "This post no longer exists.")
    return link, post


@router.get("/review/{token}")
def review_page(token: str, db: Session = Depends(get_db)):
    link, post = _link(db, token)
    link.last_seen_at = _now()
    db.commit()
    thread = db.query(ReviewFeedback).filter_by(post_id=post.id).order_by(ReviewFeedback.created_at).all()
    return {"reviewer": link.reviewer, "post": {"title": post.title, "body": post.body, "status": post.status, "version": post.version,
                                                "scheduledAt": aware(post.scheduled_at).isoformat() if post.scheduled_at else None},
            "thread": [_feedback_out(f) for f in thread], "expiresAt": aware(link.expires_at).isoformat()}


@router.post("/review/{token}/feedback", status_code=201)
def reviewer_feedback(token: str, body: FeedbackIn, db: Session = Depends(get_db)):
    link, post = _link(db, token)
    wait = core.retry_after("review:" + link.id)
    if wait:
        raise HTTPException(429, f"Too many messages. Try again in {wait} seconds.", headers={"Retry-After": str(wait)})
    if body.decision == "comment" and not body.body.strip():
        raise HTTPException(422, "Write a comment, or choose Approve or Request changes.")
    if body.decision == "changes" and not body.body.strip():
        raise HTTPException(422, "Say what should change.")
    item = ReviewFeedback(post_id=post.id, link_id=link.id, author=link.reviewer, decision=body.decision, body=body.body.strip(), post_version=post.version)
    db.add(item)
    db.commit()
    return _feedback_out(item)
