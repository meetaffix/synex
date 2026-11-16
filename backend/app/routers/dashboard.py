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


@router.get("/funnel")
def funnel(db: Session = Depends(get_db), user: models.User = Depends(get_data_user), f: dashboard_feeds.FeedFilters = Depends(_filters)):
    return dashboard_feeds.funnel(db, user.id, f)


@router.get("/campaigns")
def campaigns(db: Session = Depends(get_db), user: models.User = Depends(get_data_user), f: dashboard_feeds.FeedFilters = Depends(_filters)):
    return dashboard_feeds.campaigns(db, user.id, f)


@router.get("/export")
def export(kind: Literal["campaigns", "timeseries", "accounts"] = "campaigns", granularity: Literal["week", "day"] = "week", db: Session = Depends(get_db),
           user: models.User = Depends(get_data_user), f: dashboard_feeds.FeedFilters = Depends(_filters)):
    """The numbers the dashboard shows, as CSV. Names are neutralised so a spreadsheet never runs them as a formula."""
    import csv
    import io

    from fastapi.responses import Response
    from .. import csv_safe
    out = io.StringIO()
    writer = csv.writer(out)
    if kind == "campaigns":
        writer.writerow(["campaign", "status", "leads", "contacted", "accepted", "replied", "interested", "accepted_percent", "reply_percent"])
        for r in dashboard_feeds.campaigns(db, user.id, f):
            writer.writerow(csv_safe.row([r["name"], r["status"], r["leads"], r["contacted"], r["accepted"], r["replied"], r["interested"], r["acceptedPercent"] or "", r["replyPercent"] or ""]))
    elif kind == "timeseries":
        writer.writerow(["date", "requests", "accepted", "replies"])
        for p in dashboard_feeds.timeseries(db, user.id, f, granularity)["points"]:
            writer.writerow([p["date"], p["requests"], p["accepted"], p["replies"]])
    else:
        writer.writerow(["account_id", "requests_sent", "accepted_percent", "leads_contacted", "reply_percent"])
        for a in dashboard_feeds.accounts(db, user.id, f):
            writer.writerow([a["accountId"], a["requestsSent"], a["acceptedPercent"], a["leadsContacted"], a["replyPercent"]])
    return Response(out.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="synex-{kind}.csv"'})
