"""Add leads from a source: create a request, preview it, run it, stop it. Sources that read LinkedIn run in the outreach
worker (``collect_leads`` tasks, counted against their own daily ceiling); the others are resolved here."""
import urllib.request
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy.orm import Session

from .. import engine, lead_sources as ls, models
from ..database import get_db
from ..dedup import normalize_linkedin_url
from ..deps import get_data_user, get_manager_user

router = APIRouter(prefix="/lead-collections", tags=["lead-collections"])
MAX_SHEET_BYTES = 5_000_000


class CollectionIn(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    source: str
    account_id: str | None = None
    list_name: str | None = None
    limit: int = Field(default=50, ge=1)
    params: dict = Field(default_factory=dict)
    options: dict = Field(default_factory=dict)


class RunIn(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    list_name: str | None = None
    limit: int | None = Field(default=None, ge=1)
    options: dict | None = None


def _out(c: models.LeadCollection) -> dict:
    meta = ls.SOURCES[c.source]
    return {"id": c.id, "source": c.source, "label": meta["label"], "status": c.status, "listName": c.list_name,
            "limit": c.max_leads, "options": c.options or {}, "fetched": c.fetched_count or 0, "created": c.created_count or 0,
            "skipped": c.skipped or {}, "preview": c.preview, "estimate": ls.estimate(c.source, c.max_leads),
            "detail": c.detail, "listId": c.list_id, "accountId": c.account_id,
            "createdAt": c.created_at.isoformat() if c.created_at else None}


def _owned(db: Session, user: models.User, collection_id: str) -> models.LeadCollection:
    c = db.get(models.LeadCollection, collection_id)
    if c is None or c.user_id != user.id:
        raise HTTPException(404, "This request was not found.")
    return c


@router.get("/sources")
def sources(user: models.User = Depends(get_data_user)):
    return [{"id": k, "label": v["label"], "readsLinkedin": v["linkedin"], "available": v["built"],
             "note": v.get("note"), "maxLeads": ls.MAX_LEADS.get(k), "produces": v.get("produces", "people")} for k, v in ls.SOURCES.items()]


@router.get("/estimate")
def estimate(source: str, limit: int = 50, account_id: str | None = Query(None, alias="accountId"), db: Session = Depends(get_db),
             user: models.User = Depends(get_data_user)):
    """What a run would cost before anything is created: people, page loads, minutes, and whether it reads LinkedIn."""
    if source not in ls.SOURCES:
        raise HTTPException(422, "Unknown source.")
    left = None
    account = db.get(models.LinkedInAccount, account_id) if account_id else None
    if account is not None and account.user_id == user.id and ls.SOURCES[source]["linkedin"]:
        from ..account_policy import action_room
        left = max(0, action_room(db, account, "collect_leads", datetime.now(timezone.utc)))  # pages this account may still read today
    return {**ls.estimate(source, max(1, min(limit, ls.MAX_LEADS.get(source, limit)))), "maxPagesPerRun": ls.MAX_PAGES_PER_RUN,
            "secondsBetweenPages": list(ls.SECONDS_PER_PAGE), "pagesLeftToday": left}


@router.get("")
def recent(db: Session = Depends(get_db), user: models.User = Depends(get_data_user)):
    rows = db.query(models.LeadCollection).filter_by(user_id=user.id).order_by(models.LeadCollection.created_at.desc()).limit(20).all()
    return [_out(c) for c in rows]


@router.get("/{collection_id}")
def read(collection_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_data_user)):
    return _out(_owned(db, user, collection_id))


def _fetch_sheet(link: str) -> str:
    url = ls.sheet_export_url(link)
    if url is None:
        raise HTTPException(422, "That is not a Google Sheets link. Share the sheet so anyone with the link can view it, then paste its address.")
    try:
        with urllib.request.urlopen(url, timeout=20) as response:  # noqa: S310 - fixed host (docs.google.com), checked above
            data = response.read(MAX_SHEET_BYTES + 1)
    except Exception:  # noqa: BLE001
        raise HTTPException(422, "The sheet could not be read. Check that anyone with the link can view it.") from None
    if len(data) > MAX_SHEET_BYTES:
        raise HTTPException(422, "The sheet is too large (over 5 MB).")
    return data.decode("utf-8-sig", errors="replace")


def _lead_people(leads, default_degree=None) -> list[dict]:
    return [{"profile_url": l.linkedin_url, "name": f"{l.first_name} {l.last_name}".strip(), "headline": l.headline,
             "company": l.company, "location": l.location, "degree": l.connection_degree or default_degree}
            for l in leads if l.linkedin_url]


def _resolve_local(db: Session, user: models.User, c: models.LeadCollection) -> dict | None:
    """Stage the people of a source that does not read LinkedIn. Returns {"needsMapping": ...} when a CSV needs its columns chosen."""
    p = c.params or {}
    people: list[dict] = []
    if c.source == "urls":
        urls, rejected = ls.parse_profile_urls(p.get("text", ""))
        people = [{"profile_url": u} for u in urls]
        c.detail = f"{len(rejected)} lines were not LinkedIn profile links and were ignored." if rejected else None
    elif c.source == "csv":
        text = p.get("text") or (_fetch_sheet(p["sheetUrl"]) if p.get("sheetUrl") else "")
        try:
            headers, rows = ls.read_csv(text)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        mapping = p.get("mapping")
        if not mapping:
            return {"needsMapping": {"headers": headers, "suggested": ls.suggest_mapping(headers), "rows": len(rows)}}
        try:
            people, missing = ls.rows_to_people(rows, mapping)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        unique = {normalize_linkedin_url(p["profile_url"]) for p in people}
        c.detail = f"{len(rows)} rows read: {len(unique)} valid, {missing} without a LinkedIn profile link, {len(people) - len(unique)} repeated in the file."
    elif c.source == "lists":
        ids = p.get("listIds") or []
        leads = (db.query(models.Lead).join(models.lead_list_members).filter(
            models.Lead.user_id == user.id, models.lead_list_members.c.list_id.in_(ids)).all()) if ids else []
        people = _lead_people(leads)
    elif c.source == "inbox":
        ids = {i for (i,) in db.query(models.Conversation.lead_id).filter_by(user_id=user.id)}
        leads = db.query(models.Lead).filter(models.Lead.user_id == user.id, models.Lead.id.in_(ids)).all() if ids else []
        people = _lead_people(leads, default_degree=1)
    ls.stage(db, c, people)
    c.fetched_count = db.query(models.LeadCollectionItem).filter_by(collection_id=c.id).count()
    ls.build_preview(db, c)
    c.status = "preview_ready"
    return None


@router.post("")
def create(body: CollectionIn, db: Session = Depends(get_db), user: models.User = Depends(get_manager_user)):
    meta = ls.SOURCES.get(body.source)
    if meta is None:
        raise HTTPException(422, "Unknown source.")
    if not meta["built"]:
        raise HTTPException(409, meta.get("note") or "This source is not available yet.")
    ceiling = ls.MAX_LEADS[body.source]
    if body.limit > ceiling:
        raise HTTPException(422, f"The most you can add from this source in one go is {ceiling}.")
    account = None
    if meta["linkedin"]:
        account = db.get(models.LinkedInAccount, body.account_id or "")
        if account is None or account.user_id != user.id:
            raise HTTPException(422, "Choose the sender account that reads LinkedIn.")
        if not engine.account_is_live(account):
            raise HTTPException(409, "That sender account is not connected. Reconnect it under Sender accounts.")
        problem = ls.validate_params(body.source, body.params)
        if problem:
            raise HTTPException(422, problem)
    c = models.LeadCollection(
        user_id=user.id, account_id=account.id if account else None, source=body.source, params=body.params,
        options={"degrees": [1, 2, 3], **body.options}, list_name=(body.list_name or "").strip() or ls.default_list_name(meta["label"]),
        max_leads=body.limit, status="draft")
    db.add(c)
    db.flush()
    needs = _resolve_local(db, user, c) if not meta["linkedin"] else None
    db.commit()
    return {**_out(c), **(needs or {})}


def _queue(db: Session, c: models.LeadCollection, mode: str) -> None:
    account = db.get(models.LinkedInAccount, c.account_id or "")
    if account is None or not engine.account_is_live(account):
        raise HTTPException(409, "The sender account is not connected. Reconnect it under Sender accounts.")
    key = f"collect:{c.id}:{mode}:{datetime.now(timezone.utc).isoformat()}"
    task = engine.emit_task(db, account, "collect_leads", {"collectionId": c.id, "mode": mode}, key)
    if task is None:
        raise HTTPException(429, "This account has reached today's limit for reading LinkedIn lists. Try again tomorrow.")
    c.status = "previewing" if mode == "preview" else "queued"
    c.stop_requested = False


@router.post("/{collection_id}/preview")
def preview(collection_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_manager_user)):
    c = _owned(db, user, collection_id)
    if ls.SOURCES[c.source]["linkedin"]:
        if c.status in ("previewing", "queued", "running"):
            raise HTTPException(409, "This request is already running.")
        _queue(db, c, "preview")
    db.commit()
    return _out(c)


@router.post("/{collection_id}/run")
def run(collection_id: str, body: RunIn, db: Session = Depends(get_db), user: models.User = Depends(get_manager_user)):
    c = _owned(db, user, collection_id)
    if c.status in ("queued", "running", "completed"):
        raise HTTPException(409, "This request already ran or is running.")
    if body.list_name:
        c.list_name = body.list_name.strip()
    if body.limit:
        if body.limit > ls.MAX_LEADS[c.source]:
            raise HTTPException(422, f"The most you can add from this source in one go is {ls.MAX_LEADS[c.source]}.")
        c.max_leads = body.limit
    if body.options is not None:
        c.options = {**(c.options or {}), **body.options}
    if ls.SOURCES[c.source]["linkedin"]:
        _queue(db, c, "run")
    else:
        ls.import_collection(db, c)
        c.status = "completed"
    db.commit()
    return _out(c)


@router.post("/{collection_id}/stop")
def stop(collection_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_manager_user)):
    c = _owned(db, user, collection_id)
    c.stop_requested = True
    if c.status in ("draft", "preview_ready"):
        c.status = "stopped"
    db.commit()
    return _out(c)
