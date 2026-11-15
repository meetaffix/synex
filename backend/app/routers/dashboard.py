from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_data_user
from .. import analytics, models

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(
    db: Session = Depends(get_db), user: models.User = Depends(get_data_user)
):
    """Everything the dashboard renders in one round-trip: headline stats plus
    the recent activity feed."""
    return {
        "stats": analytics.dashboard_stats(db, user.id),
        "activity": analytics.activity_feed(db, user.id),
    }
