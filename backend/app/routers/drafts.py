"""Campaign preparation: review the drafts that will be sent, with the cost shown before any are generated.

AI drafts are made here, before launch. The engine only ever sends finished text (``engine.message_for``): the approved
draft for a lead and step, or the step's template with variables and spintax. See ``app/drafts.py``.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import drafts, engine, models
from ..config import DEEPGRAM_USD_PER_MINUTE  # noqa: F401
from ..database import get_db
from ..deps import get_data_user, get_manager_user

router = APIRouter(prefix="/campaigns/{campaign_id}/drafts", tags=["drafts"])


def _campaign(db: Session, owner: models.User, campaign_id: str) -> models.Campaign:
    campaign = db.get(models.Campaign, campaign_id)
    if campaign is None or campaign.user_id != owner.id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def _out(d: models.LeadDraft, lead: models.Lead | None, step: models.CampaignStep | None) -> dict:
    return {"id": d.id, "leadId": d.lead_id, "leadName": f"{lead.first_name} {lead.last_name}".strip() if lead else "",
            "company": lead.company if lead else None, "stepId": d.step_id, "stepOrder": step.order if step else None,
            "stepType": step.type if step else None, "body": d.body, "status": d.status, "source": d.source,
            "approvedAt": d.approved_at.isoformat() if d.approved_at else None}


@router.get("")
def list_drafts(campaign_id: str, owner: models.User = Depends(get_data_user), db: Session = Depends(get_db)):
    campaign = _campaign(db, owner, campaign_id)
    rows = db.query(models.LeadDraft).filter_by(campaign_id=campaign.id).order_by(models.LeadDraft.created_at, models.LeadDraft.id).limit(1000).all()
    leads = {l.id: l for l in db.query(models.Lead).filter(models.Lead.id.in_([r.lead_id for r in rows])).all()} if rows else {}
    steps = {s.id: s for s in campaign.steps}
    counts = {"proposed": 0, "approved": 0}
    for r in rows:
        counts[r.status] = counts.get(r.status, 0) + 1
    return {"counts": counts, "drafts": [_out(r, leads.get(r.lead_id), steps.get(r.step_id)) for r in rows], "job": drafts.job_status(campaign.id)}


@router.post("/estimate")
def estimate(campaign_id: str, owner: models.User = Depends(get_data_user), db: Session = Depends(get_db)):
    """What generating the missing drafts would cost. Shown to the user first; generation needs this count back."""
    return drafts.estimate(db, _campaign(db, owner, campaign_id))


class GenerateIn(BaseModel):
    confirmed_count: int = Field(alias="confirmedCount", ge=0)
    model_config = {"populate_by_name": True}


@router.post("/generate", status_code=202)
def generate(campaign_id: str, body: GenerateIn, owner: models.User = Depends(get_manager_user), db: Session = Depends(get_db)):
    campaign = _campaign(db, owner, campaign_id)
    shown = drafts.estimate(db, campaign)
    if body.confirmed_count != shown["count"]:
        raise HTTPException(status_code=409, detail={"message": "The number of drafts changed since the estimate was shown. Review the new estimate.", "estimate": shown})
    if shown["count"] == 0:
        raise HTTPException(status_code=409, detail={"message": "There is nothing left to draft.", "estimate": shown})
    db.rollback()  # no transaction stays open while the background job calls Deepgram
    try:
        return {"job": drafts.start_job(campaign.id, body.confirmed_count), "estimate": shown}
    except drafts.DraftError as exc:
        raise HTTPException(status_code=409, detail={"message": str(exc), "estimate": shown})


class EditIn(BaseModel):
    body: str = Field(min_length=1, max_length=1500)


@router.patch("/{draft_id}")
def edit(campaign_id: str, draft_id: str, payload: EditIn, owner: models.User = Depends(get_manager_user), db: Session = Depends(get_db)):
    campaign = _campaign(db, owner, campaign_id)
    draft = db.get(models.LeadDraft, draft_id)
    if draft is None or draft.campaign_id != campaign.id:
        raise HTTPException(status_code=404, detail="Draft not found")
    step = db.get(models.CampaignStep, draft.step_id)
    limit = 300 if step and step.type == "connection_request" else 1500
    text = payload.body.strip()
    if not text or len(text) > limit:
        raise HTTPException(status_code=422, detail=f"A message for this step is 1 to {limit} characters.")
    draft.body, draft.source, draft.status, draft.approved_at = text, "edited", "proposed", None  # an edit needs a fresh approval
    db.commit()
    return _out(draft, db.get(models.Lead, draft.lead_id), step)


class ApproveIn(BaseModel):
    draft_ids: list[str] | None = Field(default=None, alias="draftIds", max_length=1000)
    all: bool = False
    model_config = {"populate_by_name": True}


@router.post("/approve")
def approve(campaign_id: str, payload: ApproveIn, owner: models.User = Depends(get_manager_user), db: Session = Depends(get_db)):
    campaign = _campaign(db, owner, campaign_id)
    if not payload.all and not payload.draft_ids:
        raise HTTPException(status_code=422, detail="Choose drafts to approve, or approve all.")
    query = db.query(models.LeadDraft).filter_by(campaign_id=campaign.id, status="proposed")
    if not payload.all:
        query = query.filter(models.LeadDraft.id.in_(payload.draft_ids))
    now, count = datetime.now(timezone.utc), 0
    for draft in query.all():
        draft.status, draft.approved_at = "approved", now
        count += 1
    db.commit()
    return {"approved": count}


@router.delete("/{draft_id}")
def reject(campaign_id: str, draft_id: str, owner: models.User = Depends(get_manager_user), db: Session = Depends(get_db)):
    """Discard a draft: that lead then gets the step's template."""
    campaign = _campaign(db, owner, campaign_id)
    draft = db.get(models.LeadDraft, draft_id)
    if draft is None or draft.campaign_id != campaign.id:
        raise HTTPException(status_code=404, detail="Draft not found")
    db.delete(draft)
    db.commit()
    return {"ok": True}


class PreviewIn(BaseModel):
    step_type: str = Field(alias="stepType")
    lead_id: str | None = Field(default=None, alias="leadId")
    config: dict | None = None
    model_config = {"populate_by_name": True}


@router.post("/preview")
def preview(campaign_id: str, body: PreviewIn, owner: models.User = Depends(get_manager_user), db: Session = Depends(get_db)):
    """One sample message for one lead, from the settings in the open drawer (saved or not). A user action before launch; never part of sending.
    The cost of one draft is returned with it."""
    from .. import ai_prompt, providers
    campaign = _campaign(db, owner, campaign_id)
    if body.step_type not in drafts.DRAFT_STEP_TYPES:
        raise HTTPException(status_code=422, detail="Only a connection note, a message or a follow-up can be previewed.")
    try:
        config = ai_prompt.check_step_ai(body.config) if body.config is not None else None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    leads = campaign.lead_list.leads if campaign.lead_list else []
    lead = next((l for l in leads if l.id == body.lead_id), None) if body.lead_id else (leads[0] if leads else None)
    if lead is None:
        raise HTTPException(status_code=409, detail="Add a lead to this campaign's list first, so the preview has a real person to write about.")
    fields = {f: getattr(lead, f, None) or "" for f in drafts.LEAD_FIELDS}
    context = dict(campaign.ai_context or {})
    db.rollback()  # nothing stays open while the provider is called
    text, source = drafts._make_text(body.step_type, fields, {"config": config, "context": context})
    per = round(drafts.DRAFT_SECONDS_ESTIMATE / 60 * drafts.DEEPGRAM_USD_PER_MINUTE, 4) if providers.provider_name() == "deepgram" else 0.0
    return {"text": text, "source": source, "provider": providers.provider_name(), "leadName": f"{fields['first_name']} {fields['last_name']}".strip(), "estimatedUsd": per}


class RenderIn(BaseModel):
    text: str = Field(max_length=5000)
    lead_id: str | None = Field(default=None, alias="leadId")
    account_id: str | None = Field(default=None, alias="accountId")
    shuffle: int = 0
    model_config = {"populate_by_name": True}


@router.post("/render")
def render(campaign_id: str, body: RenderIn, owner: models.User = Depends(get_data_user), db: Session = Depends(get_db)):
    """A plain message as it would be sent to one lead from one sender: variables filled, spintax chosen (shuffle picks another choice).
    Names any variable the lead has no value for. Calls no AI service."""
    from .. import providers
    campaign = _campaign(db, owner, campaign_id)
    leads = campaign.lead_list.leads if campaign.lead_list else []
    lead = next((l for l in leads if l.id == body.lead_id), None) if body.lead_id else (leads[0] if leads else None)
    if lead is None:
        raise HTTPException(status_code=409, detail="No data available. Add a lead to this campaign's list to preview a message.")
    account = db.get(models.LinkedInAccount, body.account_id) if body.account_id else None
    if account is not None and account.user_id != owner.id:
        account = None
    text = providers.render_variables(body.text, lead)
    text = providers.render_sender_variables(text, account)
    if body.shuffle:
        text = providers.render_variables(body.text, _Shuffled(lead, body.shuffle))
        text = providers.render_sender_variables(text, account)
    return {"text": text, "leadName": f"{lead.first_name} {lead.last_name}".strip(), "unresolved": providers.unresolved_variables(text)}


class RewriteIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    max_length: int | None = Field(default=None, alias="maxLength", ge=1, le=5000)
    model_config = {"populate_by_name": True}


@router.post("/rewrite")
def rewrite(campaign_id: str, body: RewriteIn, owner: models.User = Depends(get_manager_user), db: Session = Depends(get_db)):
    """A humanized rewrite of the text the user wrote. A user action while writing; never part of sending. Variables are kept."""
    from .. import rewrite as rewriter
    _campaign(db, owner, campaign_id)
    db.rollback()  # nothing stays open while the provider is called
    return rewriter.humanize(body.text, body.max_length)


class _Shuffled:
    """The lead with a different spintax seed, so the preview can show another choice."""

    def __init__(self, lead, shuffle: int):
        self._lead, self.id = lead, f"{lead.id}:{shuffle}"

    def __getattr__(self, name):
        return getattr(self._lead, name)
