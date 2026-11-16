"""Carries out one ``collect_leads`` task inside the outreach worker's browser session for an account.

DB work runs in threads (the worker's pool holds one connection); the browser work is awaited. Progress is written after every
page so the screen can show it, and a stop request is read before every page.
"""
from __future__ import annotations

import asyncio
import logging

from . import lead_sources, models
from .database import SessionLocal
from .linkedin_session import collect
from .linkedin_session.actions import ActionSession

log = logging.getLogger("synex.collect")


def _load(collection_id: str) -> dict | None:
    with SessionLocal() as db:
        c = db.get(models.LeadCollection, collection_id)
        if c is None or c.status in ("stopped", "completed", "failed"):
            return None
        c.status = "previewing" if c.status in ("draft", "previewing") else "running"
        db.commit()
        return {"source": c.source, "params": dict(c.params or {}), "limit": c.max_leads}


def _stage(collection_id: str, people: list[dict]) -> None:
    with SessionLocal() as db:
        c = db.get(models.LeadCollection, collection_id)
        lead_sources.stage(db, c, people)
        c.fetched_count = db.query(models.LeadCollectionItem).filter_by(collection_id=c.id).count()
        lead_sources.build_preview(db, c)
        db.commit()


def _stop_requested(collection_id: str) -> bool:
    with SessionLocal() as db:
        c = db.get(models.LeadCollection, collection_id)
        return c is None or bool(c.stop_requested)


def _finish(collection_id: str, mode: str, failed: str | None = None) -> None:
    with SessionLocal() as db:
        c = db.get(models.LeadCollection, collection_id)
        if c is None:
            return
        if failed:
            c.status, c.detail = "failed", failed
        elif mode == "preview":
            lead_sources.build_preview(db, c)
            c.status = "preview_ready"
        else:
            if c.stop_requested:
                c.status = "stopped"
            else:
                lead_sources.import_collection(db, c)
                c.status = "completed"
        db.commit()


async def run(session: ActionSession, collection_id: str, mode: str) -> str:
    info = await asyncio.to_thread(_load, collection_id)
    if info is None:
        return "nothing_to_do"
    source, params, limit = info["source"], info["params"], info["limit"]
    preview = mode == "preview"
    wanted = lead_sources.PREVIEW_PEOPLE if preview else limit
    pages = 1 if preview else lead_sources.MAX_PAGES_PER_RUN

    async def progress(people: list[dict]) -> None:
        await asyncio.to_thread(_stage, collection_id, people)

    async def should_stop() -> bool:
        return await asyncio.to_thread(_stop_requested, collection_id)

    page = session.page
    try:
        if source == "search":
            await collect.collect_search(page, params["url"], wanted, pages, progress, should_stop)
        elif source == "post":
            per_post = max(1, wanted // max(1, len(params["urls"])))
            for url in params["urls"][: (1 if preview else None)]:
                if await should_stop():
                    break
                await collect.collect_post(page, url, params.get("reactions"), bool(params.get("comments")), per_post if not preview else wanted,
                                           progress, should_stop)
        elif source == "connections":
            await collect.collect_connections(page, params.get("filters") or {}, wanted, progress, should_stop)
        else:
            raise ValueError(f"source {source} is not collected from LinkedIn")
    except Exception as exc:  # noqa: BLE001 - recorded on the collection by type, then raised for the worker to classify
        await asyncio.to_thread(_finish, collection_id, mode, f"The read stopped early: {type(exc).__name__}")
        raise
    await asyncio.to_thread(_finish, collection_id, mode)
    return "collected"
