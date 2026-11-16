"""Carries out one ``sync_connections`` task inside the outreach worker's browser session: reads the sender's own connection list
or its received invitations, a page at a time, and keeps them on the account. Paced like every other task and counted against its
own daily ceiling. The sync state lives on the account (``management_config['connections'][kind]``)."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from . import models
from .database import SessionLocal
from .dedup import normalize_linkedin_url
from .linkedin_session import collect
from .linkedin_session.actions import ActionSession

log = logging.getLogger("synex.connections")
LIMIT = 500


def set_state(account_id: str, kind: str, **fields) -> None:
    with SessionLocal() as db:
        account = db.get(models.LinkedInAccount, account_id)
        if account is None:
            return
        config = dict(account.management_config or {})
        states = dict(config.get("connections") or {})
        states[kind] = {**(states.get(kind) or {}), **fields}
        config["connections"] = states
        account.management_config = config
        db.commit()


def upsert(account_id: str, kind: str, people: list[dict], source: str = "sync") -> int:
    """Store people; a person already stored is refreshed, never duplicated. Returns how many were new."""
    added = 0
    with SessionLocal() as db:
        existing = {row.url_key: row for row in db.query(models.AccountConnection).filter_by(account_id=account_id, kind=kind)}
        for person in people:
            key = normalize_linkedin_url(person.get("profile_url") or "")
            if not key:
                continue
            row = existing.get(key)
            if row is None:
                row = models.AccountConnection(account_id=account_id, kind=kind, url_key=key, profile_url=person["profile_url"], source=source)
                db.add(row)
                existing[key] = row
                added += 1
            row.name = (person.get("name") or row.name or "")[:200]
            row.headline = (person.get("headline") or row.headline or "")[:300]
            row.location = (person.get("location") or row.location or "")[:200]
        db.commit()
    return added


async def run(session: ActionSession, account_id: str, kind: str) -> str:
    base = getattr(getattr(session.pages, "site", None), "base_url", None) or collect.LINKEDIN_BASE
    await asyncio.to_thread(set_state, account_id, kind, status="running", detail=None)
    total = 0

    async def progress(people: list[dict]) -> None:
        nonlocal total
        total += await asyncio.to_thread(upsert, account_id, kind, people)

    async def should_stop() -> bool:
        return False

    try:
        if kind == "invitation":
            await collect.collect_invitations(session.page, LIMIT, progress, should_stop, base=base)
        else:
            await collect.collect_connections(session.page, {}, LIMIT, progress, should_stop, base=base)
    except Exception as exc:  # noqa: BLE001 - recorded by type for the screen, then raised for the worker to classify
        await asyncio.to_thread(set_state, account_id, kind, status="failed", detail=f"The read stopped early: {type(exc).__name__}")
        raise
    await asyncio.to_thread(set_state, account_id, kind, status="done", detail=None, lastSyncedAt=datetime.now(timezone.utc).isoformat(), lastAdded=total)
    return "synced"
