from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from ..errors import sanitize_errors
from ..database import get_db
from ..deps import get_current_user
from ..security import hash_password, verify_password
from ..schemas import SettingsUpdateIn, PasswordChangeIn
from .. import models

router = APIRouter(prefix="/settings", tags=["settings"])


def _parse(model, body: dict):
    try:
        return model.model_validate(body)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=sanitize_errors(e.errors()))


def _settings_out(user: models.User) -> dict:
    return {
        "notificationPrefs": user.notification_prefs or {},
        "twoFactorEnabled": False,
        "integrations": [],
    }


@router.get("")
def get_settings(user: models.User = Depends(get_current_user)):
    return _settings_out(user)


def _update(payload: SettingsUpdateIn, db: Session, user: models.User):
    if payload.notification_prefs is not None:
        prefs = dict(user.notification_prefs or {})
        prefs.update(payload.notification_prefs)
        user.notification_prefs = prefs
        flag_modified(user, "notification_prefs")

    if payload.two_factor_enabled or payload.integration is not None:
        raise HTTPException(409, "This integration is not implemented.")
    if payload.two_factor_enabled is not None:
        user.two_factor_enabled = payload.two_factor_enabled

    if payload.integration is not None:
        integ = payload.integration
        integrations = list(user.integrations or [])
        entry = next((i for i in integrations if i.get("provider") == integ.provider), None)
        if entry is None:
            entry = {"provider": integ.provider, "connected": False, "config": {}}
            integrations.append(entry)
        if integ.connected is not None:
            entry["connected"] = integ.connected
        if integ.config is not None:
            entry["config"] = integ.config
        user.integrations = integrations
        flag_modified(user, "integrations")

    db.commit()
    db.refresh(user)
    return _settings_out(user)


def _change_password(payload: PasswordChangeIn, db: Session, user: models.User):
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if not 8 <= len(payload.new_password) <= 256:
        raise HTTPException(status_code=400, detail="New password must be 8 to 256 characters")
    if payload.new_password == payload.current_password:
        raise HTTPException(status_code=400, detail="Choose a password different from the current one")
    from ..sessions import revoke_sessions
    revoke_sessions(db, user.id)
    user.hashed_password = hash_password(payload.new_password)
    db.commit()
    return {"ok": True}


@router.post("")
def write_settings(
    body: dict,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Write gateway for settings:

    * ``update``          — partial settings update (``notificationPrefs`` merged,
      ``twoFactorEnabled``, or a single ``integration`` to upsert)
    * ``change-password`` — ``currentPassword`` + ``newPassword``
    """
    action = body.get("action")
    if action == "update":
        return _update(_parse(SettingsUpdateIn, body), db, user)
    if action == "change-password":
        return _change_password(_parse(PasswordChangeIn, body), db, user)
    raise HTTPException(status_code=400, detail=f"Unknown settings action: {action!r}")
