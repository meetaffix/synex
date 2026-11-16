"""Lead sources: what can be added, how many people and how long it would take, and how staged people become leads.

Nothing here opens a browser. Sources that read LinkedIn are carried out by the outreach worker (``collect_leads`` tasks,
see ``linkedin_session/collect.py``); the rest are resolved by the API from what the person pasted or already has.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from . import models
from .dedup import normalize_linkedin_url

# id -> (label, reads LinkedIn?, people per page, built?, note shown when it is not available)
SOURCES: dict[str, dict] = {
    "post": {"label": "LinkedIn post reactions or comments", "linkedin": True, "per_page": 20, "built": True},
    "search": {"label": "LinkedIn basic search", "linkedin": True, "per_page": 10, "built": True},
    "connections": {"label": "My connections", "linkedin": True, "per_page": 40, "built": True},
    "own_posts": {"label": "People who engaged with my recent posts", "linkedin": True, "per_page": 20, "built": False,
                  "note": "Not built yet: needs the real activity page captured first."},
    "urls": {"label": "Paste profile links", "linkedin": False, "built": True},
    "csv": {"label": "CSV or Google Sheets", "linkedin": False, "built": True},
    "lists": {"label": "From my existing lists", "linkedin": False, "built": True},
    "inbox": {"label": "Inbox contacts", "linkedin": False, "built": True},
    "sales_navigator": {"label": "Sales Navigator leads", "linkedin": True, "per_page": 25, "built": False,
                        "note": "Needs a Sales Navigator subscription on the sender account, and the page captured to build it."},
    "recruiter": {"label": "Recruiter search", "linkedin": True, "per_page": 25, "built": False,
                  "note": "Needs a LinkedIn Recruiter licence on the sender account, and the page captured to build it."},
    "event": {"label": "LinkedIn event attendees", "linkedin": True, "per_page": 25, "built": False,
              "note": "Not built yet: needs a real event page captured."},
    "companies": {"label": "LinkedIn companies or Sales Navigator accounts", "linkedin": True, "per_page": 25, "built": False,
                  "note": "Not built yet: company lists produce companies, not people, and need their own capture."},
}
MAX_LEADS = {"post": 200, "search": 100, "connections": 500, "urls": 1000, "csv": 5000, "lists": 5000, "inbox": 5000}
SECONDS_PER_PAGE = (6, 14)  # random pause between page loads; the estimate uses the upper end plus load time
MAX_PAGES_PER_RUN = 15      # one collect_leads task never loads more pages than this
PREVIEW_PEOPLE = 10


def estimate(source: str, limit: int) -> dict:
    meta = SOURCES[source]
    if not meta["linkedin"]:
        return {"people": limit, "pages": 0, "minutes": 0, "reads_linkedin": False}
    pages = min(MAX_PAGES_PER_RUN, max(1, -(-limit // meta["per_page"])))
    minutes = max(1, round(pages * (SECONDS_PER_PAGE[1] + 6) / 60))
    return {"people": min(limit, pages * meta["per_page"]), "pages": pages, "minutes": minutes, "reads_linkedin": True}


def default_list_name(label: str, now: datetime | None = None) -> str:
    return f"{label} {(now or datetime.now(timezone.utc)).strftime('%d %b %Y')}"


# ---------------------------------------------------------------- parsing what the person pasted

_URL_RE = re.compile(r"https?://[^\s,;<>\"']*linkedin\.com/in/[^\s,;<>\"']+", re.I)


def parse_profile_urls(text: str) -> tuple[list[str], list[str]]:
    """(valid profile URLs in order, lines that were not profile URLs). Duplicates are left for staging to remove."""
    valid = [m.group(0).rstrip("/.)") for m in _URL_RE.finditer(text or "")]
    found = {v.lower() for v in valid}
    rejected = []
    for line in (text or "").splitlines():
        line = line.strip()
        if line and not any(f in line.lower() for f in found):
            rejected.append(line[:120])
    return valid, rejected


def sheet_export_url(link: str) -> str | None:
    """The CSV export address of a Google Sheets link (sharing must allow viewing); None when it is not one."""
    parts = urlsplit(link.strip())
    if parts.netloc != "docs.google.com":
        return None
    match = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", parts.path)
    if not match:
        return None
    gid = re.search(r"gid=(\d+)", parts.fragment + "&" + parts.query)
    return f"https://docs.google.com/spreadsheets/d/{match.group(1)}/export?format=csv" + (f"&gid={gid.group(1)}" if gid else "")


FIELDS = ("linkedin_url", "first_name", "last_name", "name", "headline", "company", "location", "email")
_GUESS = {
    "linkedin_url": ("linkedin", "profile url", "profile link", "url", "profile", "link"),
    "first_name": ("first name", "firstname", "first"),
    "last_name": ("last name", "lastname", "surname", "last"),
    "name": ("full name", "name"),
    "headline": ("headline", "title", "job title", "position"),
    "company": ("company", "organization", "organisation", "employer"),
    "location": ("location", "city", "country"),
    "email": ("email", "e-mail"),
}


def suggest_mapping(headers: list[str]) -> dict[str, str]:
    """field -> column header, guessed from the header names; the person can change every choice."""
    lowered = {h: h.strip().lower() for h in headers}
    mapping: dict[str, str] = {}
    for field, names in _GUESS.items():
        for name in names:
            hit = next((h for h, low in lowered.items() if low == name and h not in mapping.values()), None)
            hit = hit or next((h for h, low in lowered.items() if name in low and h not in mapping.values()), None)
            if hit:
                mapping[field] = hit
                break
    return mapping


def read_csv(text: str) -> tuple[list[str], list[dict]]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    rows = [dict(r) for r in reader]
    return list(reader.fieldnames or []), rows


def rows_to_people(rows: list[dict], mapping: dict[str, str]) -> tuple[list[dict], int]:
    """(people, rows without a usable LinkedIn profile URL). The LinkedIn URL column is required."""
    column = mapping.get("linkedin_url")
    if not column:
        raise ValueError("Choose which column holds the LinkedIn profile URL.")
    people, missing = [], 0
    for row in rows:
        url = (row.get(column) or "").strip()
        if not normalize_linkedin_url(url).startswith("linkedin.com/in/"):
            missing += 1
            continue
        get = lambda f: (row.get(mapping[f]) or "").strip() if mapping.get(f) else ""  # noqa: E731
        name = get("name") or f"{get('first_name')} {get('last_name')}".strip()
        people.append({"profile_url": url, "name": name, "headline": get("headline"), "company": get("company"),
                       "location": get("location"), "degree": None, "extra": {"email": get("email")} if get("email") else {}})
    return people, missing


# ---------------------------------------------------------------- staging, preview, import

def stage(db: Session, collection: models.LeadCollection, people: list[dict]) -> int:
    """Add people to the collection, one row per profile (duplicates inside the collection are dropped). Returns rows added."""
    have = {k for (k,) in db.query(models.LeadCollectionItem.url_key).filter_by(collection_id=collection.id)}
    added = 0
    for person in people:
        key = normalize_linkedin_url(person.get("profile_url"))
        if not key.startswith("linkedin.com/in/") or key in have:
            continue
        have.add(key)
        db.add(models.LeadCollectionItem(
            collection_id=collection.id, url_key=key, profile_url=person["profile_url"], name=person.get("name") or "",
            headline=person.get("headline"), company=person.get("company"), location=person.get("location"),
            degree=person.get("degree"), extra=person.get("extra") or {}))
        added += 1
    db.flush()
    return added


def degree_counts(items) -> dict[str, int]:
    counts = {"1": 0, "2": 0, "3": 0, "unknown": 0}
    for item in items:
        counts[str(item.degree) if item.degree in (1, 2, 3) else "unknown"] += 1
    return counts


def build_preview(db: Session, collection: models.LeadCollection) -> dict:
    items = db.query(models.LeadCollectionItem).filter_by(collection_id=collection.id).all()
    people = [{"name": i.name, "headline": i.headline, "company": i.company, "location": i.location, "degree": i.degree,
               "profileUrl": i.profile_url} for i in items[:PREVIEW_PEOPLE]]
    preview = {"people": people, "total": len(items), "degrees": degree_counts(items)}
    collection.preview = preview
    return preview


def exclusion_reason(db: Session, user_id: str, key: str, options: dict) -> str | None:
    """Why a person already known to Synex is left out, per the options; None when they may be added."""
    leads = [l for l in db.query(models.Lead).filter(models.Lead.user_id == user_id, models.Lead.linkedin_url != "").all()
             if normalize_linkedin_url(l.linkedin_url) == key]
    if not leads:
        return None
    lead = leads[0]
    if options.get("skip_connected") and (lead.status in ("connected", "replied", "interested") or lead.connection_degree == 1):
        return "already_connected"
    if options.get("skip_contacted") and lead.status != "new":
        return "already_contacted"
    if options.get("skip_in_campaign") and (lead.campaign_id or db.query(models.SequenceRun.id).filter_by(lead_id=lead.id).first()):
        return "already_in_campaign"
    return None


def importable_items(db: Session, collection: models.LeadCollection) -> tuple[list[models.LeadCollectionItem], dict[str, int]]:
    """The staged people that pass the degree filter and the skip options, and how many were left out for each reason."""
    options, skipped = collection.options or {}, {}
    degrees = set(options.get("degrees") or [1, 2, 3])
    keep = []
    for item in db.query(models.LeadCollectionItem).filter_by(collection_id=collection.id).order_by(models.LeadCollectionItem.id):
        if item.degree is not None and item.degree not in degrees:
            skipped["degree_filter"] = skipped.get("degree_filter", 0) + 1
            continue
        reason = exclusion_reason(db, collection.user_id, item.url_key, options)
        if reason:
            skipped[reason] = skipped.get(reason, 0) + 1
            continue
        keep.append(item)
        if len(keep) >= collection.max_leads:
            break
    return keep, skipped


def import_collection(db: Session, collection: models.LeadCollection) -> int:
    """Create the list and the leads (people already in Synex are put on the list, not duplicated). Returns people added."""
    keep, skipped = importable_items(db, collection)
    lead_list = models.LeadList(user_id=collection.user_id, name=collection.list_name or default_list_name("Leads"))
    db.add(lead_list)
    db.flush()
    existing = {normalize_linkedin_url(l.linkedin_url): l for l in
                db.query(models.Lead).filter(models.Lead.user_id == collection.user_id, models.Lead.linkedin_url != "")}
    created = 0
    for item in keep:
        lead = existing.get(item.url_key)
        if lead is None:
            first, _, last = (item.name or "").strip().partition(" ")
            lead = models.Lead(user_id=collection.user_id, first_name=first, last_name=last, headline=item.headline,
                               company=item.company or "", location=item.location, linkedin_url=item.profile_url,
                               connection_degree=item.degree, source=collection.source, status="new",
                               email=(item.extra or {}).get("email"))
            db.add(lead)
            created += 1
        elif lead.connection_degree is None and item.degree is not None:
            lead.connection_degree = item.degree
        lead_list.leads.append(lead)
    collection.list_id, collection.created_count, collection.skipped = lead_list.id, created, skipped
    return created
