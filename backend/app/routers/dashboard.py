from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_data_user
from .. import analytics, dashboard_feeds, models

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


def _filters(
    since: datetime | None = Query(None, alias="from"),
    until: datetime | None = Query(None, alias="to"),
    campaign_id: str | None = Query(None, alias="campaignId"),
    account_id: str | None = Query(None, alias="accountId"),
) -> dashboard_feeds.FeedFilters:
    def aware(value: datetime | None) -> datetime | None:
        return value if value is None or value.tzinfo else value.replace(tzinfo=timezone.utc)

    return dashboard_feeds.FeedFilters(aware(since), aware(until), campaign_id or None, account_id or None)


@router.get("/summary")
def summary(db: Session = Depends(get_db), user: models.User = Depends(get_data_user), f: dashboard_feeds.FeedFilters = Depends(_filters)):
    return dashboard_feeds.summary(db, user.id, f)


@router.get("/timeseries")
def timeseries(
    granularity: Literal["week", "day"] = "week",
    db: Session = Depends(get_db),
    user: models.User = Depends(get_data_user),
    f: dashboard_feeds.FeedFilters = Depends(_filters),
):
    return dashboard_feeds.timeseries(db, user.id, f, granularity)


@router.get("/accounts")
def accounts(db: Session = Depends(get_db), user: models.User = Depends(get_data_user), f: dashboard_feeds.FeedFilters = Depends(_filters)):
    return dashboard_feeds.accounts(db, user.id, f)
