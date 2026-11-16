"""Authenticated LinkedIn account connection API (server-side browser sessions)."""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..database import get_db
from ..deps import get_admin_user, get_current_user, get_data_user
from ..security import encrypt_secret
from ..sessions import aware
from ..linkedin_session import service, store
from ..linkedin_session.manager import SessionManager
from ..linkedin_session.proxytest import run_proxy_test
from ..linkedin_session.ratelimit import proxy_test_limiter
from ..linkedin_session.schemas import (AccountOut, AccountPatch, AttemptOut, CodeIn, ConnectIn, ProxyErrorOut,
                                        ProxyTestIn, ProxyTestOut, ReconnectLinkOut)

router = APIRouter(prefix="/linkedin-accounts", tags=["LinkedIn accounts"])
from .account_management import router as management_router
router.include_router(management_router)


@router.get("", response_model=list[AccountOut])
def list_accounts(db: Session = Depends(get_db), workspace: models.User = Depends(get_data_user),
                  actor: models.User = Depends(get_current_user)):
    rows = db.query(models.LinkedInAccount).filter(models.LinkedInAccount.user_id == workspace.id, models.LinkedInAccount.status != "deleted").order_by(models.LinkedInAccount.created_at).all()
    return [AccountOut.from_model(row, actor.id) for row in rows]


@router.post("/proxy-test", response_model=ProxyTestOut, response_model_exclude_none=True)
def proxy_test(body: ProxyTestIn, actor: models.User = Depends(get_current_user),
               workspace: models.User = Depends(get_admin_user)):
    if not proxy_test_limiter.allow(actor.id):
        raise HTTPException(429, "Too many proxy tests. Try again in a minute.")
    result = run_proxy_test(body.proxy_url)
    error = ProxyErrorOut(code=result.error_code, message=result.error_message) if result.error_code else None
    return ProxyTestOut(ok=result.ok, latency_ms=result.latency_ms, exit_ip=result.exit_ip, country=result.country, error=error)


@router.post("/connect", status_code=202, response_model=AttemptOut, response_model_exclude_none=True)
def connect(body: ConnectIn, db: Session = Depends(get_db), workspace: models.User = Depends(get_admin_user),
            actor: models.User = Depends(get_current_user), manager: SessionManager = Depends(service.get_manager)):
    service.require_allowed_proxy(body.proxy_url)
    existing = (db.query(models.LinkedInAccount)
                .filter(models.LinkedInAccount.user_id == workspace.id,
                        or_(func.lower(models.LinkedInAccount.login_identifier) == body.identifier,
                            func.lower(models.LinkedInAccount.email) == body.identifier))
                .first())
    if existing and body.sync_mode and body.sync_mode != (existing.sync_mode or "synex_only"):
        service.require_sync_owner(existing, actor.id)
    attempt = service.begin_login(manager, db, workspace_id=workspace.id, account=existing, identifier=body.identifier,
                                  password=body.password, proxy_url=body.proxy_url, timezone=body.timezone,
                                  sync_mode=body.sync_mode, connected_by=actor.id)
    return AttemptOut.from_attempt(attempt)


@router.get("/connect/{attempt_id}", response_model=AttemptOut, response_model_exclude_none=True)
def get_attempt(attempt_id: str, workspace: models.User = Depends(get_admin_user),
                manager: SessionManager = Depends(service.get_manager)):
    return AttemptOut.from_attempt(service.attempt_for(manager, attempt_id, workspace_id=workspace.id))


@router.post("/connect/{attempt_id}/code", response_model=AttemptOut, response_model_exclude_none=True)
def submit_code(attempt_id: str, body: CodeIn, workspace: models.User = Depends(get_admin_user),
                manager: SessionManager = Depends(service.get_manager)):
    attempt = service.attempt_for(manager, attempt_id, workspace_id=workspace.id)
    service.send_code(manager, attempt, body.code)
    return AttemptOut.from_attempt(attempt)


@router.delete("/connect/{attempt_id}", status_code=204)
def cancel_attempt(attempt_id: str, workspace: models.User = Depends(get_admin_user),
                   manager: SessionManager = Depends(service.get_manager)):
    manager.cancel(service.attempt_for(manager, attempt_id, workspace_id=workspace.id))
    return Response(status_code=204)


@router.post("/{account_id}/check", response_model=AccountOut)
def check_account(account_id: str, db: Session = Depends(get_db), workspace: models.User = Depends(get_admin_user),
                  actor: models.User = Depends(get_current_user), manager: SessionManager = Depends(service.get_manager)):
    account = service.owned_account(db, workspace.id, account_id)
    service.run_check(manager, account)
    db.refresh(account)
    return AccountOut.from_model(account, actor.id)


@router.patch("/{account_id}", response_model=AccountOut)
def update_account(account_id: str, body: AccountPatch, db: Session = Depends(get_db),
                   workspace: models.User = Depends(get_admin_user), actor: models.User = Depends(get_current_user)):
    account = service.owned_account(db, workspace.id, account_id)
    fields = body.model_fields_set
    service.require_allowed_proxy(body.proxy_url)
    if body.sync_mode and body.sync_mode != (account.sync_mode or "synex_only"):
        service.require_sync_owner(account, actor.id)
        account.sync_mode = body.sync_mode
    if body.daily_action_limit is not None:
        account.daily_action_limit = body.daily_action_limit
    if body.paused is not None:
        account.paused_reason = None
        account.status = "paused" if body.paused else ("active" if account.session_status == "connected" else "pending")
    if "proxy_url" in fields:
        account.proxy_url_encrypted = encrypt_secret(body.proxy_url) if body.proxy_url else None
    db.commit()
    return AccountOut.from_model(account, actor.id)


@router.post("/invite-link", response_model=ReconnectLinkOut)
def invite_link(db: Session = Depends(get_db), workspace: models.User = Depends(get_admin_user)):
    """A link for someone else to connect a new sender. The account exists, stopped at limit 0, until they sign in; their profile then names it."""
    account = models.LinkedInAccount(user_id=workspace.id, name="New sender (waiting for sign-in)", status="pending", daily_action_limit=0)
    db.add(account)
    db.commit()
    token, expires = store.issue_reconnect_token(db, account)
    return ReconnectLinkOut(url=f"{settings.frontend_url.rstrip('/')}/reconnect/{token}", expires_at=aware(expires))


@router.post("/{account_id}/reconnect-link", response_model=ReconnectLinkOut)
def reconnect_link(account_id: str, db: Session = Depends(get_db), workspace: models.User = Depends(get_admin_user)):
    account = service.owned_account(db, workspace.id, account_id)
    token, expires = store.issue_reconnect_token(db, account)
    return ReconnectLinkOut(url=f"{settings.frontend_url.rstrip('/')}/reconnect/{token}", expires_at=aware(expires))


@router.delete("/{account_id}", status_code=204)
def disconnect_account(account_id: str, db: Session = Depends(get_db), workspace: models.User = Depends(get_admin_user),
                       manager: SessionManager = Depends(service.get_manager)):
    account = service.owned_account(db, workspace.id, account_id)
    manager.cancel_for_account(account.id)
    store.wipe_session(db, account)
    db.commit()
    return Response(status_code=204)
