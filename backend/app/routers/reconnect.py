"""Public, rate-limited reconnect pages. The single-use link is the credential."""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..linkedin_session import service, store
from ..linkedin_session.manager import SessionManager
from ..linkedin_session.ratelimit import limit_connect, limit_public
from ..linkedin_session.schemas import AttemptOut, CodeIn, ReconnectInfoOut, ReconnectIn
from ..sessions import aware, digest

router = APIRouter(prefix="/reconnect", tags=["LinkedIn reconnect"], dependencies=[Depends(limit_public)])


def _account_for(db: Session, token: str):
    account = store.account_for_token(db, token)
    if account is None:
        raise HTTPException(404, "This reconnect link is invalid or has expired.")
    return account


@router.get("/{token}", response_model=ReconnectInfoOut)
def reconnect_info(token: str, db: Session = Depends(get_db)):
    account = _account_for(db, token)
    return ReconnectInfoOut(account_name=account.name, avatar_url=account.avatar_url,
                            expires_at=aware(account.reconnect_token_expires_at))


@router.post("/{token}/connect", status_code=202, response_model=AttemptOut, response_model_exclude_none=True,
             dependencies=[Depends(limit_connect)])
def reconnect(token: str, body: ReconnectIn, db: Session = Depends(get_db),
              manager: SessionManager = Depends(service.get_manager)):
    account = _account_for(db, token)
    attempt = service.begin_login(manager, db, workspace_id=account.user_id, account=account, identifier=body.identifier,
                                  password=body.password, token_digest=digest(token), sync_mode=body.sync_mode)
    return AttemptOut.from_attempt(attempt)


@router.get("/{token}/connect/{attempt_id}", response_model=AttemptOut, response_model_exclude_none=True)
def get_attempt(token: str, attempt_id: str, manager: SessionManager = Depends(service.get_manager)):
    return AttemptOut.from_attempt(service.attempt_for(manager, attempt_id, token_digest=digest(token)))


@router.post("/{token}/connect/{attempt_id}/code", response_model=AttemptOut, response_model_exclude_none=True)
def submit_code(token: str, attempt_id: str, body: CodeIn, manager: SessionManager = Depends(service.get_manager)):
    attempt = service.attempt_for(manager, attempt_id, token_digest=digest(token))
    service.send_code(manager, attempt, body.code)
    return AttemptOut.from_attempt(attempt)


@router.delete("/{token}/connect/{attempt_id}", status_code=204)
def cancel_attempt(token: str, attempt_id: str, manager: SessionManager = Depends(service.get_manager)):
    manager.cancel(service.attempt_for(manager, attempt_id, token_digest=digest(token)))
    return Response(status_code=204)
