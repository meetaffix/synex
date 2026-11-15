"""Workspace team management.

The workspace owner (or an admin seat) invites teammates by email. An invite
becomes active when a user with that email exists (immediately, or on signup —
see ``activate_pending_invites``). Members authenticate as themselves; data
routers resolve their seat to the owner's workspace with role-gated writes
(see ``deps.resolve_workspace``).
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..errors import sanitize_errors
from ..database import get_db
from ..deps import get_current_user, resolve_workspace, ROLE_RANK
from ..schemas import TeamInviteIn, TeamMemberUpdateIn
from .. import models

router = APIRouter(prefix="/team", tags=["team"])

VALID_ROLES = set(ROLE_RANK)


def _parse(model, body: dict):
    try:
        return model.model_validate(body)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=sanitize_errors(e.errors()))


def _member_out(m: models.TeamMember) -> dict:
    return {
        "id": m.id,
        "email": m.email,
        "name": m.member.full_name if m.member else None,
        "role": m.role,
        "status": m.status,
        "createdAt": m.created_at.isoformat() if m.created_at else None,
    }


def _require_admin(db: Session, user: models.User) -> models.User:
    owner, role = resolve_workspace(db, user)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Only workspace admins can manage the team")
    return owner


@router.get("")
def read_team(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """The caller's seat (role/workspace) plus the full member list in one read."""
    owner, role = resolve_workspace(db, user)
    members = (
        db.query(models.TeamMember)
        .filter(models.TeamMember.owner_id == owner.id)
        .order_by(models.TeamMember.created_at)
        .all()
    )
    return {
        "seat": {
            "workspaceOwnerId": owner.id,
            "workspaceName": owner.company or owner.full_name,
            "role": role,
            "isOwner": owner.id == user.id,
        },
        "members": [_member_out(m) for m in members],
    }


def _invite(payload: TeamInviteIn, db: Session, user: models.User):
    raise HTTPException(409, "New invitations require verified email enrollment, which is not enabled. Existing memberships are preserved.")
    owner = _require_admin(db, user)
    email = payload.email.strip().lower()
    role = (payload.role or "member").lower()
    if role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Role must be one of: {', '.join(sorted(VALID_ROLES))}")
    if email == (owner.email or "").lower():
        raise HTTPException(status_code=400, detail="The workspace owner is already an admin")
    existing = (
        db.query(models.TeamMember)
        .filter(models.TeamMember.owner_id == owner.id, models.TeamMember.email == email)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="This email is already on the team")

    invitee = db.query(models.User).filter(models.User.email == email).first()
    if invitee:
        # One workspace per user: a user already seated elsewhere can't join two.
        seated = (
            db.query(models.TeamMember)
            .filter(models.TeamMember.member_id == invitee.id, models.TeamMember.status == "active")
            .first()
        )
        if seated:
            raise HTTPException(status_code=409, detail="This user already belongs to another workspace")

    seat = models.TeamMember(
        owner_id=owner.id,
        member_id=invitee.id if invitee else None,
        email=email,
        role=role,
        status="active" if invitee else "invited",
    )
    db.add(seat)
    db.commit()
    db.refresh(seat)
    return _member_out(seat)


def _update_role(member_id: str, payload: TeamMemberUpdateIn, db: Session, user: models.User):
    owner = _require_admin(db, user)
    seat = db.get(models.TeamMember, member_id)
    if not seat or seat.owner_id != owner.id:
        raise HTTPException(status_code=404, detail="Team member not found")
    role = payload.role.lower()
    if role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Role must be one of: {', '.join(sorted(VALID_ROLES))}")
    seat.role = role
    db.commit()
    return _member_out(seat)


def _remove(member_id: str, db: Session, user: models.User):
    owner = _require_admin(db, user)
    seat = db.get(models.TeamMember, member_id)
    if not seat or seat.owner_id != owner.id:
        raise HTTPException(status_code=404, detail="Team member not found")
    db.delete(seat)
    db.commit()
    return {"ok": True}


@router.post("")
def write_team(
    body: dict,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Write gateway for team management (admin only):

    * ``invite``      — ``email`` + ``role``
    * ``update-role`` — ``memberId`` + ``role``
    * ``remove``      — ``memberId``
    """
    action = body.get("action")
    if action == "invite":
        return _invite(_parse(TeamInviteIn, body), db, user)
    if action == "update-role":
        if not body.get("memberId"):
            raise HTTPException(status_code=400, detail="memberId is required")
        return _update_role(body["memberId"], _parse(TeamMemberUpdateIn, body), db, user)
    if action == "remove":
        if not body.get("memberId"):
            raise HTTPException(status_code=400, detail="memberId is required")
        return _remove(body["memberId"], db, user)
    raise HTTPException(status_code=400, detail=f"Unknown team action: {action!r}")


def activate_pending_invites(db: Session, user: models.User) -> None:
    """Attach a newly signed-up user to any invite waiting on their email.
    Called from the signup flow."""
    pending = (
        db.query(models.TeamMember)
        .filter(
            models.TeamMember.email == (user.email or "").lower(),
            models.TeamMember.member_id.is_(None),
        )
        .all()
    )
    for seat in pending:
        seat.member_id = user.id
        seat.status = "active"
