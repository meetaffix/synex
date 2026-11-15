"""Clerk webhook: keeps a linked user's name, avatar and email in step with Clerk.

Public by necessity, so it trusts only a valid Standard Webhooks signature (see ``clerk_auth.verify_webhook``).
Delivery is at least once and unordered, so every handler is an idempotent update. A webhook never creates a user (that
happens at first sign-in, by verified email) and never deletes data: ``user.deleted`` only unlinks.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import clerk_auth, models
from ..config import settings
from ..database import get_db

log = logging.getLogger("synex.clerk")
router = APIRouter(prefix="/clerk", tags=["clerk"])


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    if not settings.clerk_webhook_secret.strip():
        raise HTTPException(status_code=503, detail="Clerk webhooks are not configured.")
    try:
        event = clerk_auth.verify_webhook(await request.body(), request.headers)
    except clerk_auth.ClerkAuthError as exc:
        log.info("Clerk webhook refused: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid webhook signature.") from None
    kind, data = event.get("type"), event.get("data") or {}
    clerk_id = data.get("id")
    user = db.query(models.User).filter(models.User.clerk_user_id == clerk_id).first() if clerk_id else None
    if user is None:
        return {"ok": True}  # nobody linked to this Clerk user yet: nothing to keep in step
    if kind == "user.deleted":
        user.clerk_user_id = None
    elif kind in ("user.created", "user.updated"):
        name = " ".join(p for p in (data.get("first_name"), data.get("last_name")) if p).strip()
        if name:
            user.full_name = name
        if data.get("image_url"):
            user.avatar_url = data["image_url"]
        email = clerk_auth.verified_primary_email(data)
        if email and email != (user.email or "").lower():
            taken = db.query(models.User).filter(func.lower(models.User.email) == email, models.User.id != user.id).first()
            if taken is None:  # never merge two rows: a clash keeps the old email
                user.email = email
    db.commit()
    return {"ok": True}
