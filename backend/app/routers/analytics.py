from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_data_user
from .. import analytics, models

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("")
def overview(
    db: Session = Depends(get_db), user: models.User = Depends(get_data_user)
):
    """Full analytics payload — the per-campaign performance breakdown is
    included under ``campaigns``."""
    return analytics.overview(db, user.id)
