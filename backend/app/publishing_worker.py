"""Run with python -m app.publishing_worker. Claims are durable and atomic.

Exactly-once external delivery is not promised: uncertain writes require review.
Only explicit 429 rejections are retried automatically. Never retry timeouts/5xx.
"""
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
import httpx
from .database import SessionLocal
from .publishing_models import Post, Connection, WorkerHeartbeat
from .publishing import log
from .linkedin import available
from .security import decrypt_secret
from .config import settings

logger = logging.getLogger("synex.publishing")
WORKER_ID = uuid.uuid4().hex


def tick(db, client=None):
    now = datetime.now(timezone.utc)
    heartbeat = db.get(WorkerHeartbeat, WORKER_ID) or WorkerHeartbeat(id=WORKER_ID)
    heartbeat.checked_at = now
    db.add(heartbeat)
    # A process may have died after sending. Do not send again automatically.
    stale = db.query(Post).filter(Post.status == "publishing", Post.claimed_at < now - timedelta(minutes=5)).all()
    for p in stale:
        count = db.query(Post).filter_by(id=p.id, status="publishing", version=p.version).update({"status": "needs_review", "error": "Worker interrupted. Check LinkedIn before creating another post.", "version": Post.version + 1}, synchronize_session=False)
        if count:
            log(db, p, "needs_review", "Interrupted delivery requires manual verification")
    db.commit()
    due = db.query(Post.id).filter(Post.status.in_(["scheduled", "retrying"]), Post.scheduled_at <= now).order_by(Post.scheduled_at).limit(20).all()
    for (post_id,) in due:
        now = datetime.now(timezone.utc)
        heartbeat.checked_at = now
        changed = db.query(Post).filter(Post.id == post_id, Post.status.in_(["scheduled", "retrying"]), Post.scheduled_at <= now).update({"status": "publishing", "claimed_at": now, "attempts": Post.attempts + 1, "version": Post.version + 1}, synchronize_session=False)
        db.commit()
        if not changed:
            continue
        db.expire_all()
        p = db.get(Post, post_id)
        log(db, p, "publishing", "Publishing request started")
        db.commit()
        acc = db.get(Connection, p.account_id)
        if not available(acc) or acc.user_id != p.user_id or "w_member_social" not in (acc.scopes or []):
            p.status, p.error = "failed", "LinkedIn connection or publishing permission unavailable. Reconnect, then reschedule."
        else:
            try:
                sender = client or httpx
                headers = {"Authorization": "Bearer " + decrypt_secret(acc.access_token), "LinkedIn-Version": settings.linkedin_api_version, "X-Restli-Protocol-Version": "2.0.0"}
                author = "urn:li:person:" + acc.subject
                payload = {"author": author, "commentary": p.body, "visibility": "PUBLIC", "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []}, "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False}
                if p.has_image:
                    from .images import prepare_media
                    try:
                        payload["content"] = prepare_media(db, sender, p, author, headers)
                    except (httpx.HTTPError, KeyError, ValueError, TypeError):
                        p.status, p.error = "failed", "LinkedIn image upload failed before post submission. Review the image and permission, then reschedule."
                        p.version += 1
                        log(db, p, p.status, p.error)
                        db.commit()
                        continue
                r = sender.post("https://api.linkedin.com/rest/posts", headers=headers, json=payload, timeout=30)
                if r.status_code == 201 and r.headers.get("x-restli-id"):
                    p.status, p.linkedin_id, p.error = "published", r.headers["x-restli-id"], None
                elif r.status_code == 429 and p.attempts < 4:
                    try:
                        delay = min(86400, max(60, int(r.headers.get("retry-after", 60 * 2 ** p.attempts))))
                    except ValueError:
                        delay = 60 * 2 ** p.attempts
                    p.status, p.scheduled_at, p.error = "retrying", now + timedelta(seconds=delay), "LinkedIn rate limit reached. A retry is scheduled."
                elif r.status_code in (401, 403):
                    p.status, p.error = "failed", "LinkedIn rejected authorization. Check product access and reconnect."
                    acc.status = "reconnect_required"
                elif 400 <= r.status_code < 500:
                    p.status, p.error = "failed", "LinkedIn rejected this post. Review the content and permissions before retrying."
                else:
                    p.status, p.error = "needs_review", "LinkedIn delivery could not be confirmed. Check your profile before creating another post."
            except httpx.HTTPError:
                p.status, p.error = "needs_review", "Connection interrupted during delivery. Check LinkedIn before creating another post."
            except Exception:
                # Credential/decode problems happen before or during dispatch; fail conservatively.
                p.status, p.error = "needs_review", "Publishing could not be confirmed. Review the connection and LinkedIn profile."
        p.version += 1
        log(db, p, p.status, p.error or "Published to LinkedIn: " + p.linkedin_id)
        db.commit()


def main():
    from .check_env import require_valid_env
    from .migrations import migrate
    require_valid_env("The publishing worker")
    migrate()
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            with SessionLocal() as db:
                tick(db)
        except Exception:
            logger.exception("Publishing worker cycle failed")
        time.sleep(15)


if __name__ == "__main__":
    main()
