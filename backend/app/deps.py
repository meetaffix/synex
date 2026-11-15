from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from .database import get_db
from . import models



def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> models.User:
    from . import clerk_auth
    if clerk_auth.enabled():  # Clerk is the only way in: cookie sessions are not accepted
        return clerk_auth.authenticate(request, db)
    from .publishing_models import SessionToken
    from .sessions import digest, aware
    from datetime import datetime, timezone
    token = request.cookies.get("synex_session")
    session = db.get(SessionToken, digest(token)) if token else None
    if not session or aware(session.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    user_id = session.user_id
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


# ---------------------------------------------------------------------------
# Workspace / team roles
#
# A user either owns their workspace (implicit admin) or holds a seat in
# someone else's via TeamMember. Data routers depend on one of the dependencies
# below; they return the *workspace owner*, so all existing user_id scoping
# transparently reads the shared workspace. The actor's role gates writes.
# ---------------------------------------------------------------------------
ROLE_RANK = {"member": 0, "manager": 1, "admin": 2}


def resolve_workspace(db: Session, user: models.User) -> tuple[models.User, str]:
    """Return (workspace owner, actor's role in it)."""
    seat = (
        db.query(models.TeamMember)
        .filter(
            models.TeamMember.member_id == user.id,
            models.TeamMember.status == "active",
        )
        .first()
    )
    if seat and seat.owner:
        return seat.owner, seat.role or "member"
    return user, "admin"


def _workspace_user(db: Session, user: models.User, min_role: str) -> models.User:
    owner, role = resolve_workspace(db, user)
    if ROLE_RANK.get(role, 0) < ROLE_RANK[min_role]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your role ({role}) does not allow this action — ask a workspace {min_role}.",
        )
    return owner


def require_role(db: Session, user: models.User, min_role: str) -> models.User:
    """Imperative role gate for write gateways: returns the workspace owner
    when the actor meets ``min_role``, else raises 403. Lets a single POST
    endpoint enforce per-action permissions."""
    return _workspace_user(db, user, min_role)


def get_data_user(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> models.User:
    """Workspace owner for read/inbox access (any role)."""
    return _workspace_user(db, user, "member")


def get_manager_user(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> models.User:
    """Workspace owner, requiring manager or admin (campaigns/leads writes)."""
    return _workspace_user(db, user, "manager")


def get_admin_user(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> models.User:
    """Workspace owner, requiring admin (accounts, team, destructive ops)."""
    return _workspace_user(db, user, "admin")
