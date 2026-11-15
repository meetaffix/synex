import json
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..errors import sanitize_errors
from ..database import get_db
from ..deps import get_data_user, get_manager_user
from ..serializers import lead_out, import_job_out
from ..schemas import (
    LeadIn, LeadUpdateIn, BulkImportIn, BulkDeleteIn, BulkStatusIn,
    LeadImportIn, ProspectReviewIn,
)
from .. import models, engine
from ..dedup import lead_dedup_key


def _parse(model, body: dict):
    """Validate the gateway body against a per-action schema, surfacing field
    errors as 422 (same as a normal typed endpoint would)."""
    try:
        return model.model_validate(body)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=sanitize_errors(e.errors()))

URL_SOURCES = {"search_url", "sales_navigator_url", "post_url", "company_url"}
_PROFILE_RE = re.compile(r"linkedin\.com/in/", re.I)

router = APIRouter(prefix="/leads", tags=["leads"])


def _merge_into(lead: models.Lead, *, company=None, job_title=None, headline=None,
                linkedin_url=None, email=None, phone=None, location=None,
                industry=None, timezone=None, lists=None) -> None:
    """Fill only the empty fields of an existing lead from an incoming row, so
    a re-import enriches rather than overwrites, and never creates a duplicate."""
    for attr, value in (
        ("company", company), ("job_title", job_title), ("headline", headline),
        ("linkedin_url", linkedin_url), ("email", email), ("phone", phone),
        ("location", location), ("industry", industry), ("timezone", timezone),
    ):
        if value and not (getattr(lead, attr) or "").strip():
            setattr(lead, attr, value)
    for ll in lists or []:
        if ll not in lead.lists:
            lead.lists.append(ll)


def _name_from_url(url: str) -> tuple[str, str]:
    m = re.search(r"/in/([^/?#]+)", url or "")
    if not m:
        return ("", "")
    words = [
        p.capitalize()
        for p in re.split(r"[-_]", m.group(1))
        if p.isalpha() and len(p) < 20
    ]
    return (words[0] if words else "", words[1] if len(words) > 1 else "")


def _owned(db: Session, user: models.User, lead_id: str) -> models.Lead:
    lead = db.get(models.Lead, lead_id)
    if not lead or lead.user_id != user.id:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


def _resolve_lists(db: Session, user: models.User, list_ids) -> list[models.LeadList]:
    lists = []
    for list_id in list_ids or []:
        ll = db.get(models.LeadList, list_id)
        if ll and ll.user_id == user.id:
            lists.append(ll)
    return lists


def _filtered_leads(
    db: Session, user: models.User,
    search: str | None, status: str | None, list_id: str | None,
) -> list[models.Lead]:
    """The workspace's leads matching the same filters the UI applies."""
    query = db.query(models.Lead).filter(models.Lead.user_id == user.id)
    if status and status != "all":
        query = query.filter(models.Lead.status == status)
    leads = query.order_by(models.Lead.created_at.desc()).all()

    if list_id and list_id != "all":
        leads = [l for l in leads if any(ll.id == list_id for ll in l.lists)]
    if search:
        s = search.lower()
        leads = [
            l
            for l in leads
            if s in f"{l.first_name} {l.last_name}".lower()
            or s in (l.company or "").lower()
            or s in (l.job_title or "").lower()
            or s in (l.headline or "").lower()
            or s in (l.email or "").lower()
            or s in (l.location or "").lower()
            or any(s in (t or "").lower() for t in (l.tags or []))
        ]
    return leads


@router.get("")
def list_leads(
    search: str | None = Query(None),
    status: str | None = Query(None),
    listId: str | None = Query(None),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_data_user),
):
    return [lead_out(l) for l in _filtered_leads(db, user, search, status, listId)]


def _create(payload: LeadIn, db: Session, user: models.User):
    lists = _resolve_lists(db, user, payload.list_ids)
    key = lead_dedup_key(
        payload.first_name, payload.last_name, payload.company, payload.linkedin_url
    )
    if key:
        for existing in db.query(models.Lead).filter(models.Lead.user_id == user.id).all():
            ek = lead_dedup_key(
                existing.first_name, existing.last_name, existing.company,
                existing.linkedin_url,
            )
            if ek == key:
                # Same person — enrich the existing lead instead of duplicating.
                _merge_into(
                    existing, company=payload.company, job_title=payload.job_title,
                    headline=payload.headline, linkedin_url=payload.linkedin_url,
                    email=payload.email, phone=payload.phone, location=payload.location,
                    industry=payload.industry, timezone=payload.timezone, lists=lists,
                )
                db.commit()
                db.refresh(existing)
                return lead_out(existing)

    lead = models.Lead(
        user_id=user.id,
        first_name=payload.first_name or "",
        last_name=payload.last_name or "",
        company=payload.company or "",
        job_title=payload.job_title or "",
        headline=payload.headline,
        linkedin_url=payload.linkedin_url or "",
        email=payload.email,
        phone=payload.phone,
        location=payload.location,
        industry=payload.industry,
        timezone=payload.timezone,
        tags=payload.tags or [],
        source="manual",
        status=payload.status or "new",
        notes=payload.notes,
    )
    lead.lists = lists
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead_out(lead)


def _bulk_create(payload: BulkImportIn, db: Session, user: models.User):
    lists = _resolve_lists(db, user, payload.list_ids)

    # Dedupe against the whole workspace AND within this batch, keyed by URL
    # (normalized) or a name+company fallback for rows that carry no URL.
    by_key: dict[str, models.Lead] = {}
    for l in db.query(models.Lead).filter(models.Lead.user_id == user.id).all():
        k = lead_dedup_key(l.first_name, l.last_name, l.company, l.linkedin_url)
        if k:
            by_key.setdefault(k, l)

    created = merged = 0
    for item in payload.leads:
        key = lead_dedup_key(item.first_name, item.last_name, item.company, item.linkedin_url)
        existing = by_key.get(key) if key else None
        if existing is not None:
            _merge_into(
                existing, company=item.company, job_title=item.job_title,
                headline=item.headline, linkedin_url=item.linkedin_url,
                email=item.email, phone=item.phone, location=item.location,
                industry=item.industry, timezone=item.timezone, lists=lists,
            )
            merged += 1
            continue
        lead = models.Lead(
            user_id=user.id,
            first_name=item.first_name or "",
            last_name=item.last_name or "",
            company=item.company or "",
            job_title=item.job_title or "",
            headline=item.headline,
            linkedin_url=item.linkedin_url or "",
            email=item.email,
            phone=item.phone,
            location=item.location,
            industry=item.industry,
            timezone=item.timezone,
            tags=item.tags or [],
            source="csv",
            status=item.status or "new",
            notes=item.notes,
        )
        lead.lists = list(lists)
        db.add(lead)
        if key:
            by_key[key] = lead
        created += 1
    db.commit()
    return {"created": created, "merged": merged}


def _dedupe(db: Session, user: models.User):
    """One-shot cleanup: merge pre-existing duplicate leads (same normalized
    URL, or same name+company when URL-less) into the earliest-created record,
    reparenting their conversations, events and runs, then deleting the extras.
    Dedup-on-import is forward-only, so this fixes a DB polluted before it."""
    leads = (
        db.query(models.Lead)
        .filter(models.Lead.user_id == user.id)
        .order_by(models.Lead.created_at.asc())
        .all()
    )
    groups: dict[str, list[models.Lead]] = {}
    for l in leads:
        k = lead_dedup_key(l.first_name, l.last_name, l.company, l.linkedin_url)
        if k:
            groups.setdefault(k, []).append(l)

    merged = 0
    for group in groups.values():
        if len(group) < 2:
            continue
        keeper = group[0]
        keeper_runs = {
            r.campaign_id
            for r in db.query(models.SequenceRun).filter(
                models.SequenceRun.lead_id == keeper.id
            )
        }
        for dup in group[1:]:
            _merge_into(
                keeper, company=dup.company, job_title=dup.job_title,
                headline=dup.headline, linkedin_url=dup.linkedin_url,
                email=dup.email, phone=dup.phone, location=dup.location,
                industry=dup.industry, lists=list(dup.lists),
            )
            if not keeper.campaign_id and dup.campaign_id:
                keeper.campaign_id = dup.campaign_id
            for conv in db.query(models.Conversation).filter(
                models.Conversation.lead_id == dup.id
            ):
                conv.lead_id = keeper.id
            for ev in db.query(models.LeadEvent).filter(
                models.LeadEvent.lead_id == dup.id
            ):
                ev.lead_id = keeper.id
            for run in db.query(models.SequenceRun).filter(
                models.SequenceRun.lead_id == dup.id
            ):
                # Avoid two runs for the same (campaign, lead) on the keeper.
                if run.campaign_id in keeper_runs:
                    db.delete(run)
                else:
                    run.lead_id = keeper.id
                    keeper_runs.add(run.campaign_id)
            db.delete(dup)
            merged += 1
    db.commit()
    return {"merged": merged}


def _delete(payload: BulkDeleteIn, db: Session, user: models.User):
    """Delete selected leads. Pass explicit ``ids`` for the rows the user
    ticked, or omit them and pass filters to clear everything matching the
    current view ('select all N → delete') without round-tripping thousands
    of ids."""
    if payload.ids is not None:
        targets = [
            lead
            for lead_id in payload.ids
            if (lead := db.get(models.Lead, lead_id))
            and lead.user_id == user.id
        ]
    else:
        targets = _filtered_leads(db, user, payload.search, payload.status, payload.list_id)

    deleted = 0
    for lead in targets:
        db.delete(lead)
        deleted += 1
    db.commit()
    return {"deleted": deleted}


def _bulk_status(payload: BulkStatusIn, db: Session, user: models.User):
    updated = 0
    for lead_id in payload.ids:
        lead = db.get(models.Lead, lead_id)
        if lead and lead.user_id == user.id:
            lead.status = payload.status
            updated += 1
    db.commit()
    return {"updated": updated}


def _review(payload: ProspectReviewIn, db: Session, user: models.User):
    """Validate + dedupe a batch of pasted URLs / CSV rows against the workspace.
    Returns counts (total/valid/duplicate/already-contacted) and the classified
    prospects so the user can review before building the list."""
    candidates: list[dict] = []
    for r in payload.rows or []:
        candidates.append({
            "firstName": r.first_name or "", "lastName": r.last_name or "",
            "company": r.company or "", "jobTitle": r.job_title or "",
            "linkedinUrl": (r.linkedin_url or "").strip(), "location": r.location,
        })
    for u in payload.urls or []:
        u = (u or "").strip()
        if not u:
            continue
        first, last = _name_from_url(u)
        candidates.append({
            "firstName": first, "lastName": last, "company": "", "jobTitle": "",
            "linkedinUrl": u, "location": None,
        })

    existing = {}
    for l in db.query(models.Lead).filter(models.Lead.user_id == user.id).all():
        k = lead_dedup_key(l.first_name, l.last_name, l.company, l.linkedin_url)
        if k:
            existing[k] = l.status

    seen: set[str] = set()
    prospects = []
    valid = dupes = contacted = invalid = 0
    for c in candidates:
        url = c["linkedinUrl"]
        is_profile = bool(url) and bool(_PROFILE_RE.search(url))
        # Key on the LinkedIn URL when it's a real profile link, otherwise fall
        # back to name+company so URL-less CSV rows still dedupe.
        key = lead_dedup_key(
            c["firstName"], c["lastName"], c["company"], url if is_profile else None
        )
        if not key:
            reason, invalid = "invalid", invalid + 1
        elif key in seen:
            reason, dupes = "duplicate", dupes + 1
        elif key in existing and existing[key] != "new":
            reason, contacted = "already_contacted", contacted + 1
        elif key in existing:
            reason, dupes = "duplicate", dupes + 1
        else:
            reason, valid = "new", valid + 1
        if key:
            seen.add(key)
        prospects.append({**c, "reason": reason, "valid": reason == "new"})

    return {
        "total": len(prospects),
        "valid": valid,
        "duplicates": dupes,
        "alreadyContacted": contacted,
        "invalid": invalid,
        "prospects": prospects,
    }


def _import(payload: LeadImportIn, db: Session, user: models.User):
    """Queue a prospect import the extension fulfils against the user's session:
    a LinkedIn URL source, or the account's own connections (with filters).
    Stays ``pending`` until the extension is active — never invents prospects."""
    if payload.source == "connections":
        job = models.ImportJob(
            user_id=user.id,
            source="connections",
            source_url=json.dumps(payload.filters or {}),
            list_ids=payload.list_ids or [],
            status="pending",
            created_count=0,
            detail="Queued — your connections are fetched when the extension is active.",
        )
    elif payload.source in URL_SOURCES:
        if not (payload.source_url or "").strip():
            raise HTTPException(status_code=400, detail="A source URL is required")
        job = models.ImportJob(
            user_id=user.id,
            source=payload.source,
            source_url=payload.source_url.strip(),
            list_ids=payload.list_ids or [],
            status="pending",
            created_count=0,
            detail="Queued — profiles import once the extension is active.",
        )
    else:
        raise HTTPException(status_code=400, detail="Unsupported import source")

    db.add(job)
    db.commit()
    db.refresh(job)
    return import_job_out(job)


# A "processing" import whose last progress report is older than this is assumed
# dead (the extension/browser was closed mid-import) and swept to "failed" so the
# UI never spins forever. "pending" jobs are NOT swept — they legitimately wait
# for the extension to check in.
IMPORT_STALL_MINUTES = 5


def _sweep_stalled_imports(db: Session, user: models.User) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=IMPORT_STALL_MINUTES)
    # Fall back to created_at when updated_at is NULL — jobs created before the
    # updated_at column existed (or that never reported progress) would otherwise
    # never satisfy ``updated_at < cutoff`` and spin forever.
    last_activity = func.coalesce(models.ImportJob.updated_at, models.ImportJob.created_at)
    stalled = (
        db.query(models.ImportJob)
        .filter(
            models.ImportJob.user_id == user.id,
            models.ImportJob.status == "processing",
            last_activity < cutoff,
        )
        .all()
    )
    if not stalled:
        return
    for job in stalled:
        job.status = "failed"
        job.detail = "Import stalled — the Synex Agent stopped responding. Re-queue to retry."
    db.commit()


@router.get("/import")
def list_import_jobs(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_data_user),
):
    _sweep_stalled_imports(db, user)
    jobs = (
        db.query(models.ImportJob)
        .filter(models.ImportJob.user_id == user.id)
        .order_by(models.ImportJob.created_at.desc())
        .limit(20)
        .all()
    )
    return [import_job_out(j) for j in jobs]


def _enrich(lead_id: str, db: Session, user: models.User):
    """Queue an enrichment task: the extension fetches the profile (and, for
    1st-degree connections, the contact info LinkedIn already shares with you)
    and reports the fields back."""
    lead = _owned(db, user, lead_id)
    if not (lead.linkedin_url or "").strip():
        raise HTTPException(status_code=400, detail="Lead has no LinkedIn URL to enrich from")

    accounts = (
        db.query(models.LinkedInAccount)
        .filter(
            models.LinkedInAccount.user_id == user.id,
            models.LinkedInAccount.agent_token.isnot(None),
        )
        .all()
    )
    if not accounts:
        raise HTTPException(
            status_code=400,
            detail="Connect LinkedIn account before enriching",
        )
    now = datetime.now(timezone.utc)
    account = next((a for a in accounts if engine.account_is_live(a, now)), accounts[0])

    db.add(
        models.AgentTask(
            account_id=account.id,
            type="enrich_profile",
            payload={"leadId": lead.id, "linkedinUrl": lead.linkedin_url},
            status="pending",
        )
    )
    db.commit()
    return {"queued": True, "detail": "Enrichment queued — runs when the extension next checks in."}


def _enrich_all(db: Session, user: models.User):
    """Queue enrich_profile tasks for every lead that has a LinkedIn URL but
    is missing company or job title data."""
    accounts = (
        db.query(models.LinkedInAccount)
        .filter(
            models.LinkedInAccount.user_id == user.id,
            models.LinkedInAccount.status == "active",
        )
        .all()
    )
    if not accounts:
        raise HTTPException(
            status_code=400,
            detail="Connect an active LinkedIn account before enriching",
        )
    now = datetime.now(timezone.utc)
    account = next((a for a in accounts if engine.account_is_live(a, now)), accounts[0])

    leads = (
        db.query(models.Lead)
        .filter(
            models.Lead.user_id == user.id,
            models.Lead.linkedin_url.isnot(None),
            models.Lead.linkedin_url != "",
        )
        .filter(
            (models.Lead.company.is_(None))
            | (models.Lead.company == "")
            | (models.Lead.job_title.is_(None))
            | (models.Lead.job_title == "")
        )
        .all()
    )
    if not leads:
        return {"queued": 0, "detail": "All leads already have company/title data."}

    # Avoid re-queuing leads that already have a pending enrich task.
    already_queued = set(
        row[0]
        for row in db.query(models.AgentTask.payload["leadId"].as_string())
        .filter(
            models.AgentTask.account_id == account.id,
            models.AgentTask.type == "enrich_profile",
            models.AgentTask.status.in_(["pending", "dispatched"]),
        )
        .all()
    )

    queued = 0
    for lead in leads:
        if str(lead.id) in already_queued:
            continue
        db.add(
            models.AgentTask(
                account_id=account.id,
                type="enrich_profile",
                payload={"leadId": lead.id, "linkedinUrl": lead.linkedin_url},
                status="pending",
            )
        )
        queued += 1
    db.commit()
    return {"queued": queued, "detail": f"Queued enrichment for {queued} leads."}


def _update(lead_id: str, payload: LeadUpdateIn, db: Session, user: models.User):
    lead = _owned(db, user, lead_id)
    data = payload.model_dump(exclude_unset=True)
    for field in (
        "first_name", "last_name", "company", "job_title", "headline",
        "linkedin_url", "email", "phone", "location", "industry", "timezone",
        "tags", "status", "notes",
    ):
        if field in data:
            setattr(lead, field, data[field])
    if payload.list_ids is not None:
        lead.lists = _resolve_lists(db, user, payload.list_ids)
    db.commit()
    db.refresh(lead)
    return lead_out(lead)


@router.post("")
def write_leads(
    body: dict,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_manager_user),
):
    """Single write gateway for leads. ``action`` selects the operation; the
    rest of the body is the payload for that action:

    * ``create``  — one lead (LeadIn fields)
    * ``bulk``    — CSV/list import: ``leads: [LeadIn]``, ``listIds``
    * ``update``  — ``id`` + changed LeadUpdateIn fields
    * ``delete``  — ``ids: [...]`` or filters (``search``/``status``/``listId``)
    * ``status``  — ``ids`` + ``status``
    * ``dedupe``  — (no payload)
    * ``review``  — ``urls`` / ``rows`` (returns a classification preview)
    * ``import``  — queue a source import (``source``/``sourceUrl``/``filters``/``listIds``)
    * ``enrich``      — ``id`` (queue a profile enrichment task)
    * ``enrich-all``  — queue enrichment for all leads missing company/title
    """
    action = body.get("action")
    if action == "create":
        return _create(_parse(LeadIn, body), db, user)
    if action == "bulk":
        return _bulk_create(_parse(BulkImportIn, body), db, user)
    if action == "update":
        if not body.get("id"):
            raise HTTPException(status_code=400, detail="id is required to update a lead")
        return _update(body["id"], _parse(LeadUpdateIn, body), db, user)
    if action == "delete":
        return _delete(_parse(BulkDeleteIn, body), db, user)
    if action == "status":
        return _bulk_status(_parse(BulkStatusIn, body), db, user)
    if action == "dedupe":
        return _dedupe(db, user)
    if action == "review":
        return _review(_parse(ProspectReviewIn, body), db, user)
    if action == "import":
        return _import(_parse(LeadImportIn, body), db, user)
    if action == "enrich":
        if not body.get("id"):
            raise HTTPException(status_code=400, detail="id is required to enrich a lead")
        return _enrich(body["id"], db, user)
    if action == "enrich-all":
        return _enrich_all(db, user)
    raise HTTPException(status_code=400, detail=f"Unknown leads action: {action!r}")
