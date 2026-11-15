"""Official LinkedIn OAuth/OIDC adapter. Never uses LinkedIn browser cookies."""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
import secrets
import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from .config import settings
from .database import get_db
from .deps import get_current_user, get_admin_user, get_data_user, require_role
from . import models
from .publishing_models import OAuthState, Connection, LinkedInIdentity, Post
from .security import encrypt_secret, decrypt_secret, hash_password
from .sessions import digest, aware, issue_session

router = APIRouter(prefix="/linkedin", tags=["LinkedIn OAuth"])
JWKS = jwt.PyJWKClient("https://www.linkedin.com/oauth/openid/jwks", timeout=15)


def configured():
    return bool(settings.linkedin_client_id and settings.linkedin_client_secret and len(settings.encryption_key) >= 32)


def begin(db, response, purpose, user_id=None, actor_id=None, target_id=None):
    if not settings.linkedin_client_id or not settings.linkedin_client_secret or (purpose == "connect" and not configured()):
        raise HTTPException(503, "LinkedIn is not configured. Ask the workspace operator to configure the client ID, client secret and encryption key.")
    state, browser, nonce = (secrets.token_urlsafe(32) for _ in range(3))
    scopes = settings.linkedin_scopes if purpose == "connect" else "openid profile email"
    if not {"openid", "profile"}.issubset(scopes.split()):
        raise HTTPException(503, "LinkedIn configuration must include openid and profile.")
    db.query(OAuthState).filter(OAuthState.expires_at < datetime.now(timezone.utc)).delete()
    db.add(OAuthState(digest=digest(state), browser_digest=digest(browser), nonce=nonce,
                      user_id=user_id, actor_id=actor_id, target_id=target_id, purpose=purpose, scopes=scopes,
                      expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)))
    db.commit()
    response.set_cookie("synex_oauth", browser, max_age=600, httponly=True,
                        secure=settings.cookie_secure, samesite="lax", path="/")
    return "https://www.linkedin.com/oauth/v2/authorization?" + urlencode({
        "response_type": "code", "client_id": settings.linkedin_client_id,
        "redirect_uri": settings.linkedin_redirect_uri, "scope": scopes,
        "state": state, "nonce": nonce,
    })


@router.get("/login")
def login(db: Session = Depends(get_db)):
    response = RedirectResponse("/", status_code=303)
    try:
        response.headers["location"] = begin(db, response, "login")
    except HTTPException:
        return RedirectResponse(settings.frontend_url + "/login?linkedin=not_configured", status_code=303)
    return response


class ConnectIn(BaseModel):
    accountId: str | None = None


@router.get("/sign-in-identity")
def sign_in_identity(db: Session = Depends(get_db), actor=Depends(get_current_user)):
    return {"linked": bool(db.query(LinkedInIdentity).filter_by(user_id=actor.id).first())}


@router.post("/link-sign-in")
def link_sign_in(response: Response, db: Session = Depends(get_db), actor=Depends(get_current_user)):
    return {"url": begin(db, response, "link", actor.id, actor.id)}


class UnlinkIn(BaseModel):
    password: str


@router.post("/unlink-sign-in")
def unlink_sign_in(payload: UnlinkIn, db: Session = Depends(get_db), actor=Depends(get_current_user)):
    from .security import verify_password
    if not verify_password(payload.password, actor.hashed_password):
        raise HTTPException(409, "Confirm your SYNEX password first. If you joined with LinkedIn, establish a password using email recovery before unlinking.")
    db.query(LinkedInIdentity).filter_by(user_id=actor.id).delete()
    db.commit()
    return {"linked": False}


@router.post("/connect")
def connect(response: Response, payload: ConnectIn | None = None, db: Session = Depends(get_db), user=Depends(get_admin_user), actor=Depends(get_current_user)):
    target = payload.accountId if payload else None
    if target:
        owned(db, user, target)
    return {"url": begin(db, response, "connect", user.id, actor.id, target)}


def exchange(code, nonce):
    with httpx.Client(timeout=20) as client:
        result = client.post("https://www.linkedin.com/oauth/v2/accessToken", data={
            "grant_type": "authorization_code", "code": code,
            "client_id": settings.linkedin_client_id, "client_secret": settings.linkedin_client_secret,
            "redirect_uri": settings.linkedin_redirect_uri,
        })
        result.raise_for_status()
        token = result.json()
        raw = token["id_token"]
        claims = jwt.decode(raw, JWKS.get_signing_key_from_jwt(raw).key, algorithms=["RS256"],
                            audience=settings.linkedin_client_id, issuer="https://www.linkedin.com",
                            options={"require": ["iss", "sub", "aud", "exp", "iat", "nonce"]})
        if not secrets.compare_digest(claims["nonce"], nonce):
            raise ValueError("Invalid nonce")
        if isinstance(claims["aud"], list) and len(claims["aud"]) > 1 and claims.get("azp") != settings.linkedin_client_id:
            raise ValueError("Invalid authorized party")
        info = client.get("https://api.linkedin.com/v2/userinfo", headers={"Authorization": "Bearer " + token["access_token"]})
        info.raise_for_status()
        profile = info.json()
        if profile["sub"] != claims["sub"]:
            raise ValueError("Subject mismatch")
        return token, profile


@router.get("/callback")
def callback(request: Request, state: str = "", code: str = "", error: str = "", db: Session = Depends(get_db)):
    record = db.get(OAuthState, digest(state))
    browser = request.cookies.get("synex_oauth", "")
    if not record or aware(record.expires_at) < datetime.now(timezone.utc) or not secrets.compare_digest(record.browser_digest, digest(browser)):
        raise HTTPException(400, "Invalid or expired authorization. Start again from SYNEX.")
    purpose, user_id, nonce, scopes = record.purpose, record.user_id, record.nonce, record.scopes
    actor_id, target_id = record.actor_id, record.target_id
    # Atomic consumption prevents callback replay across processes.
    count = db.query(OAuthState).filter_by(digest=record.digest).delete(synchronize_session=False)
    db.commit()
    if count != 1:
        raise HTTPException(400, "Authorization already used")
    destination = {"connect": "/others/publishing/connections", "link": "/settings", "login": "/login"}[purpose]
    response = RedirectResponse(settings.frontend_url + destination, status_code=303)
    response.delete_cookie("synex_oauth", path="/")
    try:
        if error or not code:
            raise ValueError("Authorization declined")
        if purpose in ("connect", "link"):
            actor = get_current_user(request=request, db=db)
            if actor.id != actor_id or (purpose == "connect" and require_role(db, actor, "admin").id != user_id):
                raise ValueError("Workspace changed")
        token, profile = exchange(code, nonce)
        identity = db.get(LinkedInIdentity, profile["sub"])
        if purpose == "login":
            if identity:
                user = db.get(models.User, identity.user_id)
            else:
                # Never link an existing SaaS account by matching email alone.
                email = profile.get("email")
                if not email or profile.get("email_verified") is not True:
                    response.headers["location"] = settings.frontend_url + "/login?linkedin=email_required"
                    return response
                if db.query(models.User).filter(func.lower(models.User.email) == email.lower()).first():
                    response.headers["location"] = settings.frontend_url + "/login?linkedin=link_existing"
                    return response
                user = models.User(email=email.lower(), full_name=profile.get("name") or "LinkedIn member", hashed_password=hash_password(secrets.token_urlsafe(48)))
                db.add(user)
                db.flush()
                db.add(LinkedInIdentity(subject=profile["sub"], user_id=user.id))
            issue_session(db, user, response)
            response.headers["location"] = settings.frontend_url + "/dashboard"
        elif purpose == "link":
            if identity and identity.user_id != actor.id:
                raise ValueError("Identity already linked")
            if not identity:
                db.add(LinkedInIdentity(subject=profile["sub"], user_id=actor.id))
            db.commit()
            response.headers["location"] += "?linkedin=linked"
        else:
            if target_id and db.get(Connection, target_id).subject != profile["sub"]:
                raise ValueError("Reconnect must use the same LinkedIn profile")
            acc = db.query(Connection).filter_by(user_id=user_id, subject=profile["sub"]).first()
            if not acc:
                acc = Connection(user_id=user_id, subject=profile["sub"])
                db.add(acc)
            acc.name, acc.picture, acc.email = profile.get("name") or "LinkedIn member", profile.get("picture"), profile.get("email")
            acc.access_token = encrypt_secret(token["access_token"])
            acc.expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(token["expires_in"]))
            # OAuth 2.0: omitted scope means the requested scopes were granted.
            acc.scopes = token.get("scope", scopes).replace(",", " ").split()
            acc.status, acc.checked_at = "connected", datetime.now(timezone.utc)
            db.commit()
            response.headers["location"] += "?linkedin=connected&account=" + acc.id
    except (httpx.HTTPError, jwt.PyJWTError, jwt.PyJWKClientError, KeyError, ValueError, TypeError, IntegrityError, HTTPException):
        db.rollback()
        response.headers["location"] = settings.frontend_url + destination + "?linkedin=failed"
    return response


def available(acc):
    return bool(acc and acc.access_token and acc.status == "connected" and acc.expires_at and aware(acc.expires_at) > datetime.now(timezone.utc))


def account_out(acc):
    live = available(acc)
    return {"id": acc.id, "name": acc.name, "picture": acc.picture, "email": acc.email,
            "status": "connected" if live else "reconnect_required", "scopes": acc.scopes or [],
            "checkedAt": aware(acc.checked_at).isoformat() if acc.checked_at else None,
            "expiresAt": aware(acc.expires_at).isoformat() if acc.expires_at else None,
            "capabilities": {
                "publishing": ("available" if "w_member_social" in (acc.scopes or []) else "requires_permission") if live else "connection_problem",
                "analytics": "requires_developer_approval", "messaging": "unavailable", "connections": "unavailable",
                "image_publishing": ("available" if "w_member_social" in (acc.scopes or []) else "requires_permission") if live else "connection_problem",
            }}


@router.get("/accounts")
def accounts(db: Session = Depends(get_db), user=Depends(get_data_user)):
    return [account_out(a) for a in db.query(Connection).filter_by(user_id=user.id).all()]


@router.get("/previous-profiles")
def previous_profiles(db: Session = Depends(get_db), user=Depends(get_data_user)):
    rows = db.query(models.LinkedInAccount.id, models.LinkedInAccount.name).filter_by(user_id=user.id).all()
    return [{"id": row.id, "name":row.name} for row in rows]


def owned(db, user, account_id):
    acc = db.get(Connection, account_id)
    if not acc or acc.user_id != user.id:
        raise HTTPException(404, "LinkedIn account not found")
    return acc


@router.post("/accounts/{account_id}/disconnect")
def disconnect(account_id: str, db: Session = Depends(get_db), user=Depends(get_admin_user)):
    acc = owned(db, user, account_id)
    if db.query(Post).filter_by(account_id=acc.id, status="publishing").first():
        raise HTTPException(409, "A publication is in progress. Wait for its result before disconnecting.")
    acc.access_token, acc.status, acc.scopes = None, "disconnected", []
    db.query(Post).filter(Post.account_id == acc.id, Post.status.in_(["scheduled", "retrying"])).update({"status": "paused", "error": "LinkedIn disconnected. Reconnect and reschedule."})
    db.commit()
    return account_out(acc)


@router.post("/accounts/{account_id}/check")
def check(account_id: str, db: Session = Depends(get_db), user=Depends(get_admin_user)):
    acc = owned(db, user, account_id)
    if not available(acc):
        raise HTTPException(409, "Reconnect this LinkedIn account first.")
    try:
        r = httpx.get("https://api.linkedin.com/v2/userinfo", headers={"Authorization": "Bearer " + decrypt_secret(acc.access_token)}, timeout=15)
        if r.status_code in (401, 403):
            acc.status = "reconnect_required"
            db.commit()
            raise HTTPException(409, "LinkedIn authorization needs renewal. Reconnect your account.")
        r.raise_for_status()
        profile = r.json()
        if profile.get("sub") != acc.subject:
            raise HTTPException(409, "Account identity could not be verified. Reconnect.")
        acc.checked_at = datetime.now(timezone.utc)
        db.commit()
    except httpx.HTTPError:
        raise HTTPException(502, "LinkedIn could not be reached. Try checking again shortly.")
    return account_out(acc)
