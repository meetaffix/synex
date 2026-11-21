"""The workspace audit log: LinkedIn actions and assistant or settings changes in one list, and an admin-only delete that leaves one line behind."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from .. import models
from ..assistant.models import AssistantAudit
from ..database import get_db
from ..deps import get_current_user, require_role, resolve_workspace
from .outreach import SEND_STEPS, describe

router = APIRouter(tags=["audit"])

SOURCES = ("all", "sends", "linkedin", "assistant", "settings")
SETTINGS_TOOLS = ("assistant_settings_changed", "audit_log_cleared")


def record(db: Session, workspace_id: str, user_id: str, action: str, detail: dict) -> None:
    """One settings-level line in the log (not committed: the caller commits with its own change)."""
    db.add(AssistantAudit(workspace_id=workspace_id, user_id=user_id, tool=action, kind="system", status="ok", arguments=detail, via="settings"))


def _linkedin(db: Session, owner: models.User, take: int, sends_only: bool = False) -> tuple[int, list[dict]]:
    q = db.query(models.AgentActivity).filter(models.AgentActivity.user_id == owner.id, models.AgentActivity.scope == "task")
    if sends_only:  # messages, invitations and other actions that reached a person: not the reads of the sender's own inbox and lists
        q = q.filter(models.AgentActivity.step.in_(SEND_STEPS))
    names = {a.id: a.name for a in db.query(models.LinkedInAccount).filter(models.LinkedInAccount.user_id == owner.id)}
    rows = q.order_by(models.AgentActivity.created_at.desc()).limit(take).all()
    tasks = {t.id: t for t in db.query(models.AgentTask).filter(models.AgentTask.id.in_([r.task_id for r in rows if r.task_id])).all()} if rows else {}
    lead_ids = {(t.payload or {}).get("leadId") for t in tasks.values()} - {None}
    leads = {l.id: l for l in db.query(models.Lead).filter(models.Lead.id.in_(lead_ids), models.Lead.user_id == owner.id).all()} if lead_ids else {}
    campaigns = {c.id: c.name for c in db.query(models.Campaign).filter(models.Campaign.id.in_({r.campaign_id for r in rows if r.campaign_id}), models.Campaign.user_id == owner.id).all()} if rows else {}
    items = []
    for r in rows:
        task = tasks.get(r.task_id)
        lead = leads.get((task.payload or {}).get("leadId")) if task else None
        person = f"{lead.first_name} {lead.last_name}".strip() if lead else None
        text = (task.payload or {}).get("message") if task else None
        items.append({"id": r.id, "at": r.created_at.isoformat(), "source": "linkedin", "who": names.get(r.account_id, "A removed account"), "action": r.step,
                      "status": r.status, "detail": describe(r.step, r.result, person, campaigns.get(r.campaign_id), text)})
    return q.count(), items


def _assistant(db: Session, owner: models.User, take: int, settings: bool) -> tuple[int, list[dict]]:
    q = db.query(AssistantAudit).filter(AssistantAudit.workspace_id == owner.id)
    q = q.filter(AssistantAudit.tool.in_(SETTINGS_TOOLS)) if settings else q.filter(AssistantAudit.tool.notin_(SETTINGS_TOOLS))
    people = {u.id: u.full_name for u in db.query(models.User).filter(models.User.id.in_({r.user_id for r in q.limit(500)}))} if q.count() else {}
    rows = q.order_by(AssistantAudit.created_at.desc()).limit(take).all()
    kind = "settings" if settings else "assistant"
    return q.count(), [{"id": r.id, "at": r.created_at.isoformat(), "source": kind, "who": people.get(r.user_id, "Someone"), "action": r.tool,
                        "status": r.status, "detail": _detail(r)} for r in rows]


def _detail(row: AssistantAudit) -> str:
    args = row.arguments or {}
    if row.tool == "audit_log_cleared":
        return f"Cleared the audit log: {args.get('removed', 0)} entries removed."
    if row.tool == "assistant_settings_changed":
        return "Changed: " + (", ".join(args.get("fields", [])) or "settings") + "."
    return (row.result or "").strip()[:200]


@router.get("/audit")
def read_audit(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), source: str = Query("all"),
               db: Session = Depends(get_db), actor: models.User = Depends(get_current_user)):
    """Newest first. ``source`` is all, linkedin (actions on LinkedIn), assistant (what the assistant did) or settings (changes and clearings)."""
    owner, role = resolve_workspace(db, actor)
    if source not in SOURCES:
        source = "all"
    take = offset + limit
    total, rows = 0, []
    for wanted, fetch in (("linkedin", lambda: _linkedin(db, owner, take, source == "sends")), ("assistant", lambda: _assistant(db, owner, take, False)), ("settings", lambda: _assistant(db, owner, take, True))):
        if source in ("all", wanted) or (source == "sends" and wanted == "linkedin"):
            count, part = fetch()
            total += count
            rows += part
    rows.sort(key=lambda r: r["at"], reverse=True)
    return {"items": rows[offset:offset + limit], "total": total, "limit": limit, "offset": offset, "canDelete": role == "admin"}


class ClearIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: str = Field(min_length=1, max_length=20)


@router.delete("/audit")
def clear_audit(body: ClearIn, db: Session = Depends(get_db), actor: models.User = Depends(get_current_user)):
    """Delete the whole audit log of the workspace. Admin only, and only with the word DELETE. One line stays: who cleared it and how many entries went."""
    from fastapi import HTTPException
    owner = require_role(db, actor, "admin")
    if body.confirm != "DELETE":
        raise HTTPException(422, "Type DELETE to confirm. Nothing was removed.")
    removed = db.query(models.AgentActivity).filter(models.AgentActivity.user_id == owner.id).delete(synchronize_session=False)
    removed += db.query(AssistantAudit).filter(AssistantAudit.workspace_id == owner.id).delete(synchronize_session=False)
    record(db, owner.id, actor.id, "audit_log_cleared", {"removed": removed})
    db.commit()
    return {"removed": removed, "remaining": 1}
