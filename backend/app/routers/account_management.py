"""Account-scoped management. Reading settings never opens LinkedIn."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import account_policy, models
from ..database import get_db
from ..deps import get_admin_user, get_current_user, get_data_user
from ..linkedin_session import service

router = APIRouter()


@router.get("/overview")
def overview(db: Session = Depends(get_db), workspace: models.User = Depends(get_data_user)):
    accounts = db.query(models.LinkedInAccount).filter_by(user_id=workspace.id).all()
    used = sum(a.status not in ("deactivated", "deleted") for a in accounts)
    return {"plan": "Free", "planPlaceholder": True, "seatsUsed": used,
            "seatsIncluded": 3, "seatsAvailable": max(0, 3 - used)}


@router.get("/{account_id}/details")
def details(account_id: str, db: Session = Depends(get_db), workspace: models.User = Depends(get_data_user),
            actor: models.User = Depends(get_current_user)):
    account = service.owned_account(db, workspace.id, account_id)
    now = datetime.now(timezone.utc)
    config = account.management_config or {}
    policy = account_policy.SenderPolicy.model_validate(config.get("policy", {}))
    campaigns = db.query(models.Campaign).filter(models.Campaign.user_id == workspace.id).all()
    active = sum(c.status == "active" and (c.account_id == account.id or account.id in (c.account_ids or [])) for c in campaigns)
    activities = db.query(models.AgentActivity).filter_by(account_id=account.id).order_by(models.AgentActivity.created_at.desc()).limit(100).all()
    return {"accountId": account.id, "lifecycle": account.status, "activeCampaigns": active,
            "canChangePrivacy": service.store.can_change_sync_mode(account, actor.id),
            "policy": policy.model_dump(by_alias=True), "usage": account_policy.usage_rows(db, account, now),
            "ssi": None, "ssiReason": "No verified LinkedIn SSI data has been collected.",
            "activity": [{"id": a.id, "step": a.step, "status": a.status, "message": a.message,
                          "createdAt": a.created_at.isoformat()} for a in activities]}


@router.put("/{account_id}/policy")
def save_policy(account_id: str, body: account_policy.SenderPolicy, db: Session = Depends(get_db),
                workspace: models.User = Depends(get_admin_user), actor: models.User = Depends(get_current_user)):
    account = service.owned_account(db, workspace.id, account_id)
    config = dict(account.management_config or {})
    previous = config.get("policy", {})
    if body.inbox_history_days != previous.get("inboxHistoryDays", 90):
        service.require_sync_owner(account, actor.id)
    proposed = body.model_dump(by_alias=True)
    # Saving an unrelated setting must not restart warm-up and lower the effective budget.
    if (previous.get("actions") != proposed["actions"] or previous.get("preset", "off") != body.preset):
        config["policyStartedAt"] = datetime.now(timezone.utc).isoformat()
    config["policy"] = proposed
    account.management_config = config
    db.commit()
    return proposed


@router.post("/{account_id}/deactivate", status_code=204)
def deactivate(account_id: str, db: Session = Depends(get_db), workspace: models.User = Depends(get_admin_user)):
    account = service.owned_account(db, workspace.id, account_id)
    account.status = "deactivated"
    account.paused_reason = "Seat deactivated by its owner. History is retained."
    db.query(models.AgentTask).filter(models.AgentTask.account_id == account.id,
                                    models.AgentTask.status == "pending").update({"status": "cancelled"})
    db.commit()
