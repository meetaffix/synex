import logging

import secrets

from datetime import datetime, timedelta, timezone



from fastapi import APIRouter, Depends, HTTPException, status, Response, Request

from pydantic import ValidationError

from sqlalchemy.orm import Session
from sqlalchemy import func



from ..errors import sanitize_errors
from ..config import settings

from ..database import get_db

from ..deps import get_current_user

from ..security import hash_password, verify_password

from ..serializers import user_out

from ..schemas import LoginIn, RegisterIn, ProfileUpdateIn, PasswordResetIn

from .. import clerk_auth, models



from ..sessions import issue_session, revoke_sessions, digest

from ..publishing_models import SessionToken



logger = logging.getLogger("synex.auth")



router = APIRouter(prefix="/auth", tags=["auth"])



RESET_TOKEN_TTL_MINUTES = 60





def _parse(model, body: dict):

    try:

        return model.model_validate(body)

    except ValidationError as e:

        raise HTTPException(status_code=422, detail=sanitize_errors(e.errors()))





def _send_reset_email(email: str, link: str) -> None:

    """Email the reset link via SMTP, or log it when SMTP isn't configured."""

    if not settings.smtp_host:

        logger.warning("Password reset unavailable: SMTP not configured")

        return

    import smtplib

    from email.message import EmailMessage



    msg = EmailMessage()

    msg["Subject"] = "Reset your Synex password"

    msg["From"] = settings.smtp_from

    msg["To"] = email

    msg.set_content(

        "We received a request to reset your Synex password.\n\n"

        f"Reset it here (link expires in {RESET_TOKEN_TTL_MINUTES} minutes):\n{link}\n\n"

        "If you didn't request this, you can safely ignore this email."

    )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:

        smtp.starttls()

        if settings.smtp_user:

            smtp.login(settings.smtp_user, settings.smtp_password)

        smtp.send_message(msg)





def _login(payload: LoginIn, db: Session, response: Response):

    user = db.query(models.User).filter(func.lower(models.User.email) == payload.email.lower()).first()

    if not user or not verify_password(payload.password, user.hashed_password):

        raise HTTPException(

            status_code=status.HTTP_401_UNAUTHORIZED,

            detail="Incorrect email or password",

        )

    issue_session(db, user, response)

    return {"user": user_out(user)}





def _register(payload: RegisterIn, db: Session, response: Response):

    if len(payload.password) < 8 or len(payload.password) > 256 or not payload.full_name.strip():

        raise HTTPException(422, "Use a name and a password of 8–256 characters")

    existing = db.query(models.User).filter(func.lower(models.User.email) == payload.email.lower()).first()

    if existing:

        raise HTTPException(

            status_code=status.HTTP_409_CONFLICT,

            detail="An account with this email already exists",

        )

    user = models.User(

        email=payload.email.lower(),

        full_name=payload.full_name,

        hashed_password=hash_password(payload.password),

    )

    db.add(user)

    db.flush()

    # Joining a team? Activate any seat invited under this email.

    from .team import activate_pending_invites



    # Invitation activation requires verified email; never auto-join here.

    db.commit()

    db.refresh(user)

    issue_session(db, user, response)

    return {"user": user_out(user)}





@router.post("")

def auth_gateway(body: dict, response: Response, db: Session = Depends(get_db)):

    """Single entry point for unauthenticated auth actions. ``action`` selects:



    * ``login``          — ``email`` + ``password`` → ``{user, token}``

    * ``register``       — ``fullName`` + ``email`` + ``password`` → ``{user, token}``

    * ``reset-request``  — ``email`` (emails a reset link; always returns ok)

    * ``reset-confirm``  — ``token`` + ``password`` (sets the new password)

    """

    action = body.get("action")

    if clerk_auth.enabled() and action in ("login", "register", "reset-request", "reset-confirm"):

        raise HTTPException(status_code=410, detail="Sign-in is handled by Clerk. Use the sign-in page.")

    if action == "login":

        return _login(_parse(LoginIn, body), db, response)

    if action == "register":

        return _register(_parse(RegisterIn, body), db, response)

    if action == "reset-request":

        return _request_reset(_parse(PasswordResetIn, body), db)

    if action == "reset-confirm":

        return _confirm_reset(_parse(PasswordResetIn, body), db)

    raise HTTPException(status_code=400, detail=f"Unknown auth action: {action!r}")





def _request_reset(payload: PasswordResetIn, db: Session) -> dict:
    if not settings.smtp_host:
        raise HTTPException(503, "Password-reset email delivery is not configured. Contact your workspace operator.")

    if not payload.email:

        raise HTTPException(status_code=400, detail="An email is required")

    user = db.query(models.User).filter(func.lower(models.User.email) == payload.email.lower()).first()

    if user:

        token = secrets.token_urlsafe(32)

        db.add(

            models.PasswordResetToken(

                user_id=user.id,

                token=digest(token),

                expires_at=datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_TTL_MINUTES),

            )

        )

        db.commit()

        link = f"{settings.frontend_url.rstrip('/')}/reset-password?token={token}"

        try:

            _send_reset_email(user.email, link)

        except Exception:

            logger.exception("failed to send password reset email")

    return {"ok": True}





def _confirm_reset(payload: PasswordResetIn, db: Session) -> dict:

    if not payload.password:

        raise HTTPException(status_code=400, detail="A new password is required")

    record = (

        db.query(models.PasswordResetToken)

        .filter(models.PasswordResetToken.token == digest(payload.token or ""))

        .first()

    )

    now = datetime.now(timezone.utc)

    expires = record.expires_at if record else None

    if expires is not None and expires.tzinfo is None:

        expires = expires.replace(tzinfo=timezone.utc)

    if not record or record.used or expires is None or expires < now:

        raise HTTPException(

            status_code=status.HTTP_400_BAD_REQUEST,

            detail="This reset link is invalid or has expired — request a new one.",

        )

    if len(payload.password) < 8:

        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    user = db.get(models.User, record.user_id)

    if not user:

        raise HTTPException(status_code=400, detail="This reset link is invalid")

    user.hashed_password = hash_password(payload.password)

    record.used = True

    revoke_sessions(db, user.id)

    db.commit()

    return {"ok": True}





@router.get("/me")

def me(user: models.User = Depends(get_current_user)):

    return user_out(user)





@router.put("/me")

def update_me(

    payload: ProfileUpdateIn,

    user: models.User = Depends(get_current_user),

    db: Session = Depends(get_db),

):

    data = payload.model_dump(exclude_unset=True)

    if data.get("full_name") is not None:

        user.full_name = data["full_name"]

    if data.get("email") and data["email"] != user.email:

        raise HTTPException(409, "Email changes require verification and are not enabled.")

    if "company" in data:

        user.company = data["company"]



    if "avatar_url" in data:

        user.avatar_url = data["avatar_url"]

    db.commit()

    db.refresh(user)

    return user_out(user)





@router.post("/logout")

def logout(request: Request, response: Response, db: Session = Depends(get_db)):

    if clerk_auth.enabled():  # the session lives in Clerk; the browser signs out there

        return {"ok": True}

    db.query(SessionToken).filter_by(digest=digest(request.cookies.get("synex_session", ""))).delete()

    db.commit()

    response.delete_cookie("synex_session", path="/")

    return {"ok": True}

