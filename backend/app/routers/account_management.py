"""Account-scoped management. Reading settings never opens LinkedIn."""
import csv
import io
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import account_policy, connections_runner, engine, models
from ..database import get_db
from ..dedup import normalize_linkedin_url
from ..deps import get_admin_user, get_current_user, get_data_user, get_manager_user
from ..linkedin_session import service

router = APIRouter()


ACCEPTED = {"connected", "replied", "interested", "not_interested"}
REPLIED = {"replied", "interested", "not_interested"}


def _percent(part: int, whole: int):
    return round(100 * part / whole, 1) if whole else None


def _performance(db: Session, workspace_id: str, accounts, campaigns) -> dict:
    """Per account: of the people its campaigns contacted, how many accepted, and of those how many replied."""
    by_campaign = {}
    for lead in db.query(models.Lead.campaign_id, models.Lead.status).filter(models.Lead.user_id == workspace_id, models.Lead.campaign_id.isnot(None)):
        counts = by_campaign.setdefault(lead.campaign_id, {"invited": 0, "accepted": 0, "replied": 0})
        if lead.status != "new":
            counts["invited"] += 1
        counts["accepted"] += lead.status in ACCEPTED
        counts["replied"] += lead.status in REPLIED
    out = {}
    for account in accounts:
        total = {"invited": 0, "accepted": 0, "replied": 0}
        for campaign in campaigns:
            if campaign.account_id == account.id or account.id in (campaign.account_ids or []):
                for key, value in by_campaign.get(campaign.id, {}).items():
                    total[key] += value
        out[account.id] = {**total, "acceptedPercent": _percent(total["accepted"], total["invited"]), "replyPercent": _percent(total["replied"], total["accepted"])}
    return out


@router.get("/overview")
def overview(db: Session = Depends(get_db), workspace: models.User = Depends(get_data_user)):
    accounts = db.query(models.LinkedInAccount).filter_by(user_id=workspace.id).all()
    used = sum(a.status not in ("deactivated", "deleted") for a in accounts)
    now = datetime.now(timezone.utc)
    campaigns = db.query(models.Campaign).filter(models.Campaign.user_id == workspace.id).all()
    performance = _performance(db, workspace.id, accounts, campaigns)
    per_account = {}
    for account in accounts:
        rows = {row["action"]: row for row in account_policy.usage_rows(db, account, now)}
        pick = lambda action: {k: rows[action][k] for k in ("used", "low", "high", "budget")}  # noqa: E731
        per_account[account.id] = {"connections": pick("send_invite"), "messages": pick("send_message"),
                                   "smart": account_policy.policy_for(account).preset != "off", "performance": performance[account.id]}
    return {"plan": "Free", "planPlaceholder": True, "seatsUsed": used,
            "seatsIncluded": 3, "seatsAvailable": max(0, 3 - used), "accounts": per_account}


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


# ---- connection list and received invitations ---------------------------------------------------------------------

Kind = Literal["connection", "invitation"]
SYNC_NOTE = "Synex reads your connections a little at a time, so a long list takes a while to fill."


def _sync_state(account: models.LinkedInAccount, kind: str) -> dict:
    state = ((account.management_config or {}).get("connections") or {}).get(kind) or {}
    return {"status": state.get("status", "idle"), "detail": state.get("detail"), "lastSyncedAt": state.get("lastSyncedAt"), "lastAdded": state.get("lastAdded")}


def _row(row: models.AccountConnection) -> dict:
    return {"id": row.id, "name": row.name, "headline": row.headline or "", "location": row.location or "", "profileUrl": row.profile_url, "source": row.source}


@router.get("/{account_id}/connections")
def list_connections(account_id: str, kind: Kind = "connection", q: str = "", limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                     db: Session = Depends(get_db), workspace: models.User = Depends(get_data_user)):
    account = service.owned_account(db, workspace.id, account_id)
    query = db.query(models.AccountConnection).filter_by(account_id=account.id, kind=kind)
    if q.strip():
        like = f"%{q.strip().lower()}%"
        query = query.filter(or_(func.lower(models.AccountConnection.name).like(like), func.lower(models.AccountConnection.headline).like(like),
                                 func.lower(models.AccountConnection.location).like(like)))
    total = query.count()
    rows = query.order_by(models.AccountConnection.name, models.AccountConnection.id).offset(offset).limit(limit).all()
    return {"items": [_row(row) for row in rows], "total": total, "sync": _sync_state(account, kind), "note": SYNC_NOTE}


class ReloadIn(BaseModel):
    kind: Kind = "connection"


@router.post("/{account_id}/connections/reload", status_code=202)
def reload_connections(account_id: str, body: ReloadIn, db: Session = Depends(get_db), workspace: models.User = Depends(get_manager_user)):
    account = service.owned_account(db, workspace.id, account_id)
    if not engine.account_is_live(account):
        raise HTTPException(409, "This account is not connected. Reconnect it first.")
    if _sync_state(account, body.kind)["status"] in ("queued", "running"):
        raise HTTPException(409, "A read of this list is already running.")
    key = f"sync_connections:{account.id}:{body.kind}:{datetime.now(timezone.utc).isoformat()}"
    task = engine.emit_task(db, account, "sync_connections", {"accountId": account.id, "kind": body.kind}, key)
    if task is None:
        raise HTTPException(429, "This account has reached today's limit for reading its connection list. Try again tomorrow.")
    config = dict(account.management_config or {})
    states = dict(config.get("connections") or {})
    states[body.kind] = {**(states.get(body.kind) or {}), "status": "queued", "detail": None}
    config["connections"] = states
    account.management_config = config
    db.commit()
    return {"sync": _sync_state(account, body.kind), "note": SYNC_NOTE}


@router.get("/{account_id}/connections/export")
def export_connections(account_id: str, kind: Kind = "connection", db: Session = Depends(get_db), workspace: models.User = Depends(get_data_user)):
    account = service.owned_account(db, workspace.id, account_id)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["linkedin_url", "name", "headline", "location"])
    for row in db.query(models.AccountConnection).filter_by(account_id=account.id, kind=kind).order_by(models.AccountConnection.name):
        # A spreadsheet runs text that starts with = + - @ as a formula: neutralise it.
        writer.writerow([("'" + v if v[:1] in "=+-@" else v) for v in (row.profile_url, row.name or "", row.headline or "", row.location or "")])
    name = "connections.csv" if kind == "connection" else "invitations.csv"
    return Response(out.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})


class ImportIn(BaseModel):
    csv_text: str = Field(alias="csv", max_length=2_000_000)
    kind: Kind = "connection"

    model_config = {"populate_by_name": True}


@router.post("/{account_id}/connections/import")
def import_connections(account_id: str, body: ImportIn, db: Session = Depends(get_db), workspace: models.User = Depends(get_manager_user)):
    account = service.owned_account(db, workspace.id, account_id)
    reader = csv.DictReader(io.StringIO(body.csv_text.lstrip("﻿")))
    fields = {(name or "").strip().lower().replace(" ", "_"): name for name in (reader.fieldnames or [])}
    column = next((fields[k] for k in ("linkedin_url", "linkedin", "profile_url", "url") if k in fields), None)
    if column is None:
        raise HTTPException(422, "The file needs a column named linkedin_url (one LinkedIn profile address per row).")
    people, invalid, seen = [], 0, set()
    duplicates_in_file = 0
    for row in reader:
        url = (row.get(column) or "").strip()
        key = normalize_linkedin_url(url) if "linkedin.com/in/" in url.lower() else None
        if not key:
            invalid += 1
            continue
        if key in seen:
            duplicates_in_file += 1
            continue
        seen.add(key)
        people.append({"profile_url": url, "name": (row.get(fields.get("name", "")) or "").strip(), "headline": (row.get(fields.get("headline", "")) or "").strip(),
                       "location": (row.get(fields.get("location", "")) or "").strip()})
    added = connections_runner.upsert(account.id, body.kind, people, source="csv")
    return {"added": added, "alreadyStored": len(people) - added, "duplicatesInFile": duplicates_in_file, "invalid": invalid}
