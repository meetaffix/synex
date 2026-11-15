"""Campaign preparation: AI drafts are generated BEFORE launch, never while sending.

The engine sends only finished text (``engine.message_for``): the approved draft for that lead and step, else the
step's template with variables and spintax. This module is the only place a campaign reaches an AI service.

Rules it keeps:
* the user sees an estimate (count, minutes, dollars) first, and generation runs only for the count they saw;
* a cap per campaign (``DRAFT_CAP_PER_CAMPAIGN``) and small batches (``DRAFT_BATCH_SIZE``);
* no database transaction is open while Deepgram is called: the plan is read and its session closed, every draft is
  written afterwards in a short transaction of its own, so a retried transaction can never repeat a Deepgram call;
* drafts start as ``proposed`` and are sent only once approved.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Callable

from sqlalchemy.orm import Session

from . import engine, models
from .config import DEEPGRAM_USD_PER_MINUTE, DRAFT_BATCH_SIZE, DRAFT_CAP_PER_CAMPAIGN, DRAFT_SECONDS_ESTIMATE
from .database import SessionLocal
from .providers import DeepgramAIProvider, TemplateAIProvider, get_ai_provider, render_variables

log = logging.getLogger(__name__)

DRAFT_STEP_TYPES = ("connection_request", "message", "follow_up")
LEAD_FIELDS = ("first_name", "last_name", "company", "job_title", "location", "headline", "industry")


class DraftError(Exception):
    def __init__(self, message: str, estimate: dict | None = None):
        super().__init__(message)
        self.estimate = estimate


def _targets(db: Session, campaign: models.Campaign) -> tuple[list[tuple[models.Lead, models.CampaignStep]], int, int]:
    """(leads and steps still without a draft, up to the cap; how many were available before the cap; drafts that exist)."""
    steps = [s for s in engine.sorted_steps(campaign) if s.type in DRAFT_STEP_TYPES]
    leads = sorted(campaign.lead_list.leads if campaign.lead_list else [], key=lambda l: (l.created_at, l.id))
    have = {(d.step_id, d.lead_id) for d in db.query(models.LeadDraft).filter_by(campaign_id=campaign.id).all()}
    wanted = []
    for lead in leads:
        if engine.stop_reason_for(campaign, lead) or not (lead.linkedin_url or "").strip():
            continue
        for step in steps:
            if step.type == "connection_request" and (lead.status in engine.ACCEPTED_STATES or (campaign.audience_source or {}).get("type") == "connections"):
                continue  # the engine skips this step for them, so there is nothing to draft
            if (step.id, lead.id) not in have:
                wanted.append((lead, step))
    room = max(DRAFT_CAP_PER_CAMPAIGN - len(have), 0)
    return wanted[:room], len(wanted), len(have)


def estimate(db: Session, campaign: models.Campaign) -> dict:
    """What generating the missing drafts would do and cost, shown to the user before anything is generated."""
    targets, available, existing = _targets(db, campaign)
    using_ai = isinstance(get_ai_provider(), DeepgramAIProvider)
    seconds = len(targets) * DRAFT_SECONDS_ESTIMATE
    return {
        "count": len(targets), "available": available, "existing": existing, "cap": DRAFT_CAP_PER_CAMPAIGN,
        "capped": available > len(targets), "provider": "deepgram" if using_ai else "template",
        "secondsPerDraft": DRAFT_SECONDS_ESTIMATE, "estimatedSeconds": seconds, "usdPerMinute": DEEPGRAM_USD_PER_MINUTE,
        "estimatedUsd": round(seconds / 60 * DEEPGRAM_USD_PER_MINUTE, 4) if using_ai else 0.0,
        "note": ("Each draft is one short Deepgram Voice Agent connection, billed by the minute. This is an estimate."
                 if using_ai else "Deepgram is not configured, so drafts come from the templates and cost nothing."),
    }


def _make_text(step_type: str, lead_fields: dict) -> tuple[str, str]:
    """One draft's text and its source. The only AI call in a campaign's life; always outside a transaction."""
    fields = {"first_name": lead_fields.get("first_name"), "company": lead_fields.get("company"), "job_title": lead_fields.get("job_title")}
    source = "ai"
    try:
        provider = get_ai_provider()
        body = provider.generate_message(step_type, "friendly", fields)
        if not isinstance(provider, DeepgramAIProvider):
            source = "template"
    except Exception:  # Deepgram unreachable, refused or empty: the local template is still a usable starting point
        body, source = TemplateAIProvider().generate_message(step_type, "friendly", fields), "template"
    body = render_variables(body, SimpleNamespace(**lead_fields))
    if step_type == "connection_request" and len(body) > 300:
        body = body[:300].rstrip()  # LinkedIn's limit for a connection note
    return body, source


def generate_drafts(campaign_id: str, confirmed_count: int, session_factory: Callable[[], Session] = SessionLocal,
                    progress: Callable[[dict], None] | None = None) -> dict:
    """Generate the missing drafts, in batches, for exactly the count the user confirmed."""
    with session_factory() as db:  # read the plan, then close the session: nothing is open while Deepgram is called
        campaign = db.get(models.Campaign, campaign_id)
        if campaign is None:
            raise DraftError("Campaign not found.")
        user_id = campaign.user_id
        targets, _, _ = _targets(db, campaign)
        current = estimate(db, campaign)
        if confirmed_count != len(targets):
            raise DraftError("The number of drafts changed since the estimate was shown. Review the new estimate.", current)
        plan = [{"lead_id": lead.id, "step_id": step.id, "step_type": step.type,
                 "fields": {**{f: getattr(lead, f, None) or "" for f in LEAD_FIELDS}, "id": lead.id}} for lead, step in targets]
    done = {"requested": len(plan), "created": 0, "ai": 0, "templateFallback": 0}
    for start in range(0, len(plan), DRAFT_BATCH_SIZE):
        batch = plan[start:start + DRAFT_BATCH_SIZE]
        results = [(item, *_make_text(item["step_type"], item["fields"])) for item in batch]  # no database session open here
        with session_factory() as db:  # one short transaction per batch, holding no external call
            for item, body, source in results:
                exists = db.query(models.LeadDraft.id).filter_by(campaign_id=campaign_id, step_id=item["step_id"], lead_id=item["lead_id"]).first()
                if exists:
                    continue
                db.add(models.LeadDraft(user_id=user_id, campaign_id=campaign_id, step_id=item["step_id"], lead_id=item["lead_id"],
                                        body=body, status="proposed", source=source))
                done["created"] += 1
                done["ai" if source == "ai" else "templateFallback"] += 1
            db.commit()
        if progress:
            progress(dict(done))
    return done


# ---- an in-process background job per campaign, so the request that starts it returns at once ----------------------
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def start_job(campaign_id: str, confirmed_count: int) -> dict:
    with _jobs_lock:
        running = _jobs.get(campaign_id)
        if running and running["state"] == "running":
            raise DraftError("Drafts are already being generated for this campaign.")
        job = _jobs[campaign_id] = {"state": "running", "requested": confirmed_count, "created": 0, "ai": 0, "templateFallback": 0,
                                    "startedAt": datetime.now(timezone.utc).isoformat(), "error": None}

    def work():
        try:
            def tick(done):
                with _jobs_lock:
                    job.update(done)
            result = generate_drafts(campaign_id, confirmed_count, progress=tick)
            with _jobs_lock:
                job.update(result)
                job["state"] = "done"
        except Exception as exc:  # noqa: BLE001
            log.exception("draft generation failed for campaign %s", campaign_id)
            with _jobs_lock:
                job["state"], job["error"] = "failed", "Generating drafts stopped. The drafts made so far are kept."
            if isinstance(exc, DraftError):
                job["error"] = str(exc)

    thread = threading.Thread(target=work, name=f"drafts-{campaign_id[:8]}", daemon=True)
    job["thread"] = thread
    thread.start()
    return public_job(job)


def public_job(job: dict | None) -> dict | None:
    return None if job is None else {k: v for k, v in job.items() if k != "thread"}


def job_status(campaign_id: str) -> dict | None:
    with _jobs_lock:
        return public_job(_jobs.get(campaign_id))


def wait_for_job(campaign_id: str, timeout: float = 30.0) -> None:
    """Block until the campaign's job ends (used by tests)."""
    job = _jobs.get(campaign_id)
    if job and job.get("thread"):
        job["thread"].join(timeout)
