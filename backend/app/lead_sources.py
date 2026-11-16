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

from . import csv_safe, dnc, models
from .dedup import normalize_linkedin_url

# id -> (label, reads LinkedIn?, people per page, built?, note shown when it is not available)
SOURCES: dict[str, dict] = {
    "post": {"label": "LinkedIn post reactions or comments", "linkedin": True, "per_page": 20, "built": True},
    "search": {"label": "LinkedIn basic search", "linkedin": True, "per_page": 10, "built": True},
    "connections": {"label": "My connections", "linkedin": True, "per_page": 40, "built": True},
    "own_posts": {"label": "People who engaged with my recent posts", "linkedin": True, "per_page": 20, "built": True},
    "urls": {"label": "Paste profile links", "linkedin": False, "built": True},
    "csv": {"label": "CSV or Google Sheets", "linkedin": False, "built": True},
    "lists": {"label": "From my existing lists", "linkedin": False, "built": True},
    "inbox": {"label": "Inbox contacts", "linkedin": False, "built": True},
    "sales_navigator": {"label": "Sales Navigator leads", "linkedin": True, "per_page": 25, "built": True,
                        "note": "Needs a Sales Navigator subscription on the sender account. Unverified on real LinkedIn: no account with access."},
    "recruiter": {"label": "Recruiter search", "linkedin": True, "per_page": 25, "built": True,
                  "note": "Needs a LinkedIn Recruiter licence on the sender account. Unverified on real LinkedIn: no account with access."},
    "event": {"label": "LinkedIn event attendees", "linkedin": True, "per_page": 25, "built": True,
              "note": "The sender account must be marked as attending the event."},
    "companies": {"label": "LinkedIn companies", "linkedin": True, "per_page": 10, "built": True, "produces": "companies"},
    "sales_nav_accounts": {"label": "Sales Navigator accounts", "linkedin": True, "per_page": 25, "built": True, "produces": "companies"},
    "group": {"label": "LinkedIn group members", "linkedin": True, "per_page": 20, "built": False,
              "note": "Coming soon: LinkedIn only shows a group's member list to its members, and the page has not been captured yet."},
}
COMPANY_SOURCES = {k for k, v in SOURCES.items() if v.get("produces") == "companies"}
MAX_LEADS = {"post": 200, "search": 100, "connections": 500, "urls": 1000, "csv": 5000, "lists": 5000, "inbox": 5000,
             "event": 500, "own_posts": 200, "sales_navigator": 2500, "recruiter": 2500, "companies": 500, "sales_nav_accounts": 500}

_POST_RE = re.compile(r"linkedin\.com/(feed/update/urn:li:(activity|ugcPost|share):\d+|posts/[^\s?]+)", re.I)
_URL_PATTERNS = {
    "search": ("linkedin.com/search/results/people", "Paste a LinkedIn people-search results address (it contains /search/results/people)."),
    "sales_navigator": ("linkedin.com/sales/", "Paste a Sales Navigator people search or list address (it starts with linkedin.com/sales/)."),
    "recruiter": ("linkedin.com/talent/", "Paste a LinkedIn Recruiter search address (it contains linkedin.com/talent/)."),
    "event": ("linkedin.com/events/", "Paste a LinkedIn event address (it contains linkedin.com/events/)."),
    "companies": ("linkedin.com/search/results/companies", "Paste a LinkedIn company-search results address (it contains /search/results/companies)."),
    "sales_nav_accounts": ("linkedin.com/sales/search/company", "Paste a Sales Navigator account search address (it contains /sales/search/company)."),
}


def validate_params(source: str, params: dict) -> str | None:
    """The reason a source's pasted address is wrong, in words the person can act on; None when it is acceptable."""
    if source == "post":
        urls = [u for u in params.get("urls", []) if "linkedin.com" in u]
        if not urls:
            return "Paste at least one LinkedIn post link."
        bad = [u for u in urls if not _POST_RE.search(u)]
        if bad:
            return "That is not a post link. Open the post, use its three-dot menu, choose Copy link to post, and paste it here."
        return None
    if source in _URL_PATTERNS:
        needle, message = _URL_PATTERNS[source]
        return None if needle in (params.get("url") or "").lower() else message
    return None
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
    return csv_safe.parse(text, dialect=dialect)  # row limit, no binary content; raises csv_safe.CsvTooLarge (a ValueError)


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
    companies = collection.source in COMPANY_SOURCES
    for person in people:
        if companies:
            url = person.get("company_url") or ""
            key = re.sub(r"^https?://(www\.)?", "", url.lower()).rstrip("/")
            ok = key.startswith("linkedin.com/company/")
        else:
            url = person.get("profile_url")
            key = normalize_linkedin_url(url)
            ok = key.startswith("linkedin.com/in/")
        if not ok or key in have:
            continue
        have.add(key)
        db.add(models.LeadCollectionItem(
            collection_id=collection.id, url_key=key, profile_url=url, name=person.get("name") or "",
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


def exclusion_reason(db: Session, user_id: str, key: str, options: dict, company: str | None = None) -> str | None:
    """Why a person already known to Synex is left out, per the options; None when they may be added."""
    if dnc.blocked_key(db, user_id, key, company):
        return "do_not_contact"
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
        reason = exclusion_reason(db, collection.user_id, item.url_key, options, item.company)
        if reason:
            skipped[reason] = skipped.get(reason, 0) + 1
            continue
        keep.append(item)
        if len(keep) >= collection.max_leads:
            break
    return keep, skipped


def _import_companies(db: Session, collection: models.LeadCollection) -> int:
    """Company sources fill a company list, not the leads: companies are not people and are never messaged."""
    items = db.query(models.LeadCollectionItem).filter_by(collection_id=collection.id).order_by(models.LeadCollectionItem.id).limit(collection.max_leads).all()
    company_list = models.CompanyList(user_id=collection.user_id, name=collection.list_name or default_list_name("Companies"))
    db.add(company_list)
    db.flush()
    for item in items:
        db.add(models.CompanyEntry(list_id=company_list.id, key=item.url_key, name=item.name, url=item.profile_url, industry=item.headline, location=item.location))
    collection.list_id, collection.created_count, collection.skipped = company_list.id, len(items), {}
    return len(items)


def import_collection(db: Session, collection: models.LeadCollection) -> int:
    """Create the list and the leads (people already in Synex are put on the list, not duplicated). Returns people added."""
    if collection.source in COMPANY_SOURCES:
        return _import_companies(db, collection)
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
