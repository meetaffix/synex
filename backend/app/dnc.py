"""The do-not-contact list: people (by LinkedIn profile) and companies (by name or LinkedIn company page).

It is checked three times: when people are imported, when a campaign launches, and again just before every action is carried out, so adding someone
stops anything still queued for them. A company is matched by its name with case, spaces and punctuation ignored.
"""
import re

from sqlalchemy.orm import Session

from . import models
from .dedup import normalize_linkedin_url

_COMPANY_URL = re.compile(r"linkedin\.com/(?:company|school)/([^/?#\s]+)", re.I)


def company_key(value: str | None) -> str:
    """Case, spaces and punctuation do not matter: 'Acme, Inc.' and 'acme-inc' are the same company."""
    text = (value or "").strip()
    match = _COMPANY_URL.search(text)
    if match:
        text = match.group(1)
    return re.sub(r"[^a-z0-9]", "", text.lower())


def person_key(url: str | None) -> str:
    key = normalize_linkedin_url(url)
    return key if key.startswith("linkedin.com/in/") else ""


def blocked_key(db: Session, user_id: str, profile_key: str, company: str | None) -> str | None:
    """'person' or 'company' when the list covers this profile or company; None otherwise."""
    if profile_key and db.query(models.DoNotContact.id).filter_by(user_id=user_id, kind="person", key=profile_key).first():
        return "person"
    ckey = company_key(company)
    if ckey and db.query(models.DoNotContact.id).filter_by(user_id=user_id, kind="company", key=ckey).first():
        return "company"
    return None


def blocked(db: Session, user_id: str, lead: models.Lead) -> str | None:
    return blocked_key(db, user_id, person_key(lead.linkedin_url), lead.company)


def add_entries(db: Session, user_id: str, kind: str, entries: list[dict], source: str) -> dict:
    """entries: {'value': text, 'name': optional}. Returns counts; duplicates and unusable lines are never added twice."""
    have = {k for (k,) in db.query(models.DoNotContact.key).filter_by(user_id=user_id, kind=kind)}
    added = already = invalid = 0
    for entry in entries:
        value = (entry.get("value") or "").strip()
        key = person_key(value) if kind == "person" else company_key(value)
        if not value or not key:
            invalid += 1
            continue
        if key in have:
            already += 1
            continue
        have.add(key)
        name = (entry.get("name") or "").strip() or (value if kind == "company" else "")
        db.add(models.DoNotContact(user_id=user_id, kind=kind, key=key, name=name[:200], profile_url=value[:500] if kind == "person" else None, source=source))
        added += 1
    db.flush()
    return {"added": added, "alreadyListed": already, "invalid": invalid}
