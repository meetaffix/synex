import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from .publishing_models import SessionToken
from .config import settings


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def issue_session(db, user, response):
    db.query(SessionToken).filter(SessionToken.expires_at < datetime.now(timezone.utc)).delete()
    token = secrets.token_urlsafe(48)
    expires = datetime.now(timezone.utc) + timedelta(hours=12)
    db.add(SessionToken(digest=digest(token), user_id=user.id, expires_at=expires))
    db.commit()
    response.set_cookie("synex_session", token, httponly=True, secure=settings.cookie_secure,
                        samesite="lax", max_age=43200, path="/")


def revoke_sessions(db, user_id):
    db.query(SessionToken).filter_by(user_id=user_id).delete()
