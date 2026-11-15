"""Every tool the assistant has. To add one, define its arguments and handler here and ``register`` it; the
agent's function list, permission checks, audit log and confirmation flow all come from ``registry``.

Not available yet (the assistant says so plainly): sending messages, replying in the inbox, launching a
campaign for the first time, deleting anything, importing from LinkedIn searches. There is deliberately no tool
for any of them, and ``run_tool`` answers an unknown name with "not available yet".
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .. import analytics, engine, models
from ..deps import ROLE_RANK
from ..config import DAILY_ACTION_CEILING, DAILY_TYPE_CEILINGS, WEEKLY_INVITE_CEILING
from ..linkedin_session.schemas import AccountPatch
from ..providers import get_ai_provider, render_variables
from ..routers import accounts as accounts_router
from ..routers import campaigns as campaigns_router
from ..routers import lead_lists as lists_router
from ..routers import leads as leads_router
from ..routers import templates as templates_router
from ..schemas import BulkImportIn, CampaignIn, CampaignUpdateIn, LeadIn, LeadListIn, StepIn, TemplateIn, TemplateUpdateIn
from ..serializers import account_display_status
from .registry import Plan, Tool, ToolContext, ToolError, _errors_text, register

INVITE_CEILING = DAILY_TYPE_CEILINGS["send_invite"]
MESSAGE_CEILING = DAILY_TYPE_CEILINGS["send_message"]
STEP_TYPES = ("connection_request", "message", "follow_up", "wait", "profile_visit", "follow")
STATUSES = ("draft", "active", "paused", "completed")


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")  # an argument the schema does not name is refused, never ignored


class NoArgs(Args):
    pass


def _name(lead: models.Lead) -> str:
    return f"{lead.first_name} {lead.last_name}".strip() or "Unnamed lead"


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _owned(ctx: ToolContext, model, record_id: str, label: str):
    row = ctx.db.get(model, record_id)
    if row is None or row.user_id != ctx.workspace.id:
        raise ToolError(f"I can't find that {label} in this workspace.")
    return row


def _parse(model, **data):
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ToolError(_errors_text(exc)) from exc


# =========================================================================================== read tools =========
def _dashboard(ctx: ToolContext, a: NoArgs) -> dict:
    db, ws = ctx.db, ctx.workspace
    stats = analytics.dashboard_stats(db, ws.id)
    campaigns = db.query(models.Campaign).filter_by(user_id=ws.id).all()
    accounts = db.query(models.LinkedInAccount).filter_by(user_id=ws.id).all()
    by_status: dict[str, int] = {}
    for c in campaigns:
        by_status[c.status] = by_status.get(c.status, 0) + 1
    needs = [x.name for x in accounts if account_display_status(x) not in ("connected", "paused")]
    unread = db.query(models.Conversation).filter_by(user_id=ws.id, unread=True).count()
    return {"stats": stats, "campaignsByStatus": by_status, "senderAccounts": len(accounts),
            "accountsNeedingAttention": needs, "unreadConversations": unread}


def _campaign_row(c: models.Campaign) -> dict:
    return {"id": c.id, "name": c.name, "status": c.status, "listName": c.lead_list.name if c.lead_list else None,
            "accountName": c.account.name if c.account else None, "dailyConnectionLimit": engine.campaign_type_limit(c, "send_invite"),
            "dailyMessageLimit": engine.campaign_type_limit(c, "send_message"), "pausedReason": c.paused_reason}


class SearchCampaigns(Args):
    query: str = Field("", description="Part of the campaign name. Empty lists all.", max_length=100)
    status: Literal["draft", "active", "paused", "completed"] | None = None
    limit: int = Field(10, ge=1, le=20)


def _search_campaigns(ctx: ToolContext, a: SearchCampaigns) -> dict:
    q = ctx.db.query(models.Campaign).filter_by(user_id=ctx.workspace.id)
    if a.status:
        q = q.filter(models.Campaign.status == a.status)
    rows = [c for c in q.order_by(models.Campaign.created_at.desc()).all() if a.query.lower() in c.name.lower()]
    return {"total": len(rows), "campaigns": [_campaign_row(c) for c in rows[: a.limit]]}


class CampaignId(Args):
    campaign_id: str


def _get_campaign(ctx: ToolContext, a: CampaignId) -> dict:
    c = _owned(ctx, models.Campaign, a.campaign_id, "campaign")
    steps = [{"order": s.order, "type": s.type, "delayHours": s.delay_hours,
              "message": (s.message or "")[:300]} for s in engine.sorted_steps(c)]
    leads = c.lead_list.leads if c.lead_list else []
    return {**_campaign_row(c), "description": (c.description or "")[:300], "steps": steps, "leadCount": len(leads),
            "schedule": {"timezone": c.timezone, "days": c.working_days, "startHour": c.start_hour, "endHour": c.end_hour},
            "launchedAt": _iso(c.launched_at)}


def _explain_campaign(ctx: ToolContext, a: CampaignId) -> dict:
    c = _owned(ctx, models.Campaign, a.campaign_id, "campaign")
    now = datetime.now(timezone.utc)
    reasons: list[str] = []
    fix: list[str] = []
    if c.status == "draft":
        reasons.append("It is still a draft and has never been launched.")
        fix.append("Finish the sequence, pick a lead list and a connected sender account, then launch it from the campaign page.")
    elif c.status == "completed":
        reasons.append("Every lead has finished the sequence.")
    elif c.status == "paused":
        if c.paused_reason:
            reasons.append(f"Synex paused it automatically: {c.paused_reason}.")
        else:
            reasons.append("It was paused by a person (no automatic reason is recorded).")
        if c.consecutive_failures:
            reasons.append(f"{c.consecutive_failures} actions failed in a row.")
            fix.append("Open the campaign's monitor, check the failed actions, then resume.")
    accounts = engine.campaign_accounts(ctx.db, c)
    if not accounts:
        reasons.append("No sender account is attached.")
        fix.append("Attach a connected sender account.")
    for acct in accounts:
        if not engine.account_is_live(acct, now):
            reasons.append(f"Sender account {acct.name} is not live ({account_display_status(acct)}).")
            fix.append(f"Reconnect or resume {acct.name} under Sender accounts.")
    if not (c.lead_list and c.lead_list.leads):
        reasons.append("Its lead list is empty or missing.")
        fix.append("Add leads to the campaign's list.")
    if c.status == "active" and not reasons:
        reasons.append("It is running normally.")
    return {"campaign": c.name, "status": c.status, "reasons": reasons, "whatToDo": fix}


class SearchLeads(Args):
    query: str = Field("", description="Part of a name, company or job title.", max_length=100)
    status: str | None = Field(None, max_length=30)
    list_id: str | None = None
    limit: int = Field(10, ge=1, le=20)


def _search_leads(ctx: ToolContext, a: SearchLeads) -> dict:
    q = ctx.db.query(models.Lead).filter_by(user_id=ctx.workspace.id)
    if a.status:
        q = q.filter(models.Lead.status == a.status)
    rows = q.order_by(models.Lead.created_at.desc()).all()
    if a.list_id:
        rows = [l for l in rows if any(x.id == a.list_id for x in l.lists)]
    needle = a.query.lower().strip()
    if needle:
        rows = [l for l in rows if needle in f"{_name(l)} {l.company} {l.job_title}".lower()]
    return {"total": len(rows), "leads": [{"id": l.id, "name": _name(l), "company": l.company, "jobTitle": l.job_title,
                                            "status": l.status} for l in rows[: a.limit]]}


class LeadId(Args):
    lead_id: str


def _get_lead(ctx: ToolContext, a: LeadId) -> dict:
    l = _owned(ctx, models.Lead, a.lead_id, "lead")
    events = (ctx.db.query(models.LeadEvent).filter_by(lead_id=l.id).order_by(models.LeadEvent.created_at.desc()).limit(15).all())
    convo = ctx.db.query(models.Conversation).filter_by(lead_id=l.id).first()
    messages = []
    if convo:
        for m in sorted(convo.messages, key=lambda m: m.sent_at or datetime.min.replace(tzinfo=timezone.utc))[-5:]:
            messages.append({"direction": m.direction, "text": m.body[:200], "at": _iso(m.sent_at)})
    return {"id": l.id, "name": _name(l), "company": l.company, "jobTitle": l.job_title, "headline": l.headline,
            "location": l.location, "industry": l.industry, "status": l.status, "tags": l.tags or [],
            "lists": [x.name for x in l.lists], "notes": (l.notes or "")[:500],
            "history": [{"type": e.type, "detail": (e.detail or "")[:120], "at": _iso(e.created_at)} for e in events],
            "recentMessages": messages}


def _list_lists(ctx: ToolContext, a: NoArgs) -> dict:
    rows = ctx.db.query(models.LeadList).filter_by(user_id=ctx.workspace.id).order_by(models.LeadList.created_at.desc()).all()
    return {"lists": [{"id": r.id, "name": r.name, "description": (r.description or "")[:120], "leadCount": len(r.leads)} for r in rows]}


class SearchTemplates(Args):
    query: str = Field("", max_length=100)


def _list_templates(ctx: ToolContext, a: SearchTemplates) -> dict:
    rows = ctx.db.query(models.Template).filter_by(user_id=ctx.workspace.id).order_by(models.Template.created_at.desc()).all()
    rows = [t for t in rows if a.query.lower() in f"{t.name} {t.category}".lower()]
    return {"templates": [{"id": t.id, "name": t.name, "category": t.category, "body": t.body[:300]} for t in rows[:20]]}


def _account_row(x: models.LinkedInAccount, now: datetime) -> dict:
    return {"id": x.id, "name": x.name, "status": account_display_status(x), "live": engine.account_is_live(x, now),
            "dailyActionLimit": engine.configured_daily_limit(x), "todayLimitAfterWarmup": engine.effective_daily_limit(x, now),
            "actionsUsedToday": x.daily_actions_used or 0, "pausedReason": x.paused_reason}


def _list_accounts(ctx: ToolContext, a: NoArgs) -> dict:
    now = datetime.now(timezone.utc)
    rows = ctx.db.query(models.LinkedInAccount).filter_by(user_id=ctx.workspace.id).order_by(models.LinkedInAccount.created_at).all()
    return {"accounts": [_account_row(x, now) for x in rows]}


class AccountId(Args):
    account_id: str


def _explain_account(ctx: ToolContext, a: AccountId) -> dict:
    x = _owned(ctx, models.LinkedInAccount, a.account_id, "sender account")
    now = datetime.now(timezone.utc)
    status = account_display_status(x)
    reasons: list[str] = []
    fix: list[str] = []
    if x.status == "paused":
        reasons.append(f"It is paused: {x.paused_reason}." if x.paused_reason else "It was paused by a person.")
        fix.append("Resume it (the assistant can prepare that).")
    if status == "needs_reconnect":
        reasons.append("LinkedIn asked for a fresh sign-in, so the saved browser session no longer works.")
        fix.append("A workspace admin reconnects it under Sender accounts. The assistant cannot sign in to LinkedIn.")
    elif status == "restricted":
        reasons.append("LinkedIn has restricted the account.")
        fix.append("Stop outreach on it and check the account on LinkedIn yourself.")
    elif status in ("disconnected", "pending"):
        reasons.append("It has no working saved session yet.")
        fix.append("Use Connect LinkedIn account under Sender accounts.")
    if engine.account_is_live(x, now) and engine.remaining_capacity(x, now) <= 0:
        reasons.append("It has used today's action allowance, including the warm-up ramp.")
        fix.append("It continues tomorrow. Raising the limit does not help while warm-up caps the day.")
    if not reasons:
        reasons.append("It is connected and healthy.")
    return {"account": x.name, "status": status, "reasons": reasons, "whatToDo": fix}


# =========================================================================================== drafting tools =====
class DraftMessage(Args):
    step_type: Literal["connection_request", "message", "follow_up"] = "message"
    tone: str = Field("friendly", max_length=40)
    lead_id: str | None = Field(None, description="Personalise from this lead's stored data.")
    template_id: str | None = Field(None, description="Start from this template's text.")
    text: str | None = Field(None, max_length=1500, description="Your own draft. Pass it so the user sees it with an Insert button.")
    field_label: str | None = Field(None, max_length=60, description="Where it will go, e.g. 'connection note'.")


def _draft(ctx: ToolContext, a: DraftMessage) -> dict:
    lead = _owned(ctx, models.Lead, a.lead_id, "lead") if a.lead_id else None
    template = _owned(ctx, models.Template, a.template_id, "template") if a.template_id else None
    if a.text and a.text.strip():
        body = a.text.strip()
    elif template:
        body = template.body
    else:
        known = {"first_name": lead.first_name, "company": lead.company, "job_title": lead.job_title} if lead else {}
        try:  # the existing drafting provider; falls back to the local template when no LLM is configured or it fails
            body = get_ai_provider().generate_message(a.step_type, a.tone, known)
        except Exception:
            from ..providers import TemplateAIProvider
            body = TemplateAIProvider().generate_message(a.step_type, a.tone, known)
    if lead:
        body = render_variables(body, lead)
    limit = 300 if a.step_type == "connection_request" else 1500
    warnings = []
    if len(body) > limit:
        body = body[:limit].rstrip()
        warnings.append(f"Shortened to {limit} characters, LinkedIn's limit for this kind of message.")
    leftovers = [t for t in ("{{first_name}}", "{{company}}", "{{job_title}}") if t in body]
    if leftovers:
        warnings.append("Still contains merge fields that fill in per lead: " + ", ".join(leftovers))
    return {"draft": body, "warnings": warnings, "note": "Shown to the user with an Insert button. Nothing was saved or sent.",
            "_ui": [{"type": "draft", "text": body, "label": a.field_label or {"connection_request": "connection note"}.get(a.step_type, "message"),
                     "warnings": warnings}]}


class ProposeSequence(Args):
    goal: str = Field(max_length=300, description="What the campaign should achieve, e.g. 'book demos with fintech CTOs'.")
    audience: str | None = Field(None, max_length=200)
    include_profile_visit: bool = True


def _propose_sequence(ctx: ToolContext, a: ProposeSequence) -> dict:
    steps = []
    if a.include_profile_visit:
        steps.append({"type": "profile_visit", "purpose": "A quiet first touch that shows the profile was viewed."})
    steps += [
        {"type": "connection_request", "purpose": "Short, specific note (under 300 characters). No pitch yet."},
        {"type": "wait", "delayHours": 48},
        {"type": "message", "purpose": "Thank them for connecting and give one reason this is relevant to their role."},
        {"type": "wait", "delayHours": 72},
        {"type": "follow_up", "purpose": "A light nudge with one clear, easy ask that serves the goal."},
    ]
    return {"goal": a.goal, "steps": steps,
            "suggestedLimits": {"dailyConnectionLimit": 15, "dailyMessageLimit": 30, "workingDays": [1, 2, 3, 4, 5], "hours": "09:00-17:00 in the leads' timezone"},
            "safety": [f"Connection requests are capped at {INVITE_CEILING} a day and {WEEKLY_INVITE_CEILING} a week per account.",
                       "Stop the sequence when someone replies.", "Three touches after connecting is enough."],
            "next": "Write the copy for each message step using only facts the user gave you, then call create_campaign_draft. Never invent facts about people."}


class SuggestLimits(Args):
    account_id: str | None = Field(None, description="Use this account's age. Omit for a brand-new account.")
    account_age: Literal["new", "warming", "established"] | None = None


def _suggest_limits(ctx: ToolContext, a: SuggestLimits) -> dict:
    age = a.account_age
    if a.account_id:
        x = _owned(ctx, models.LinkedInAccount, a.account_id, "sender account")
        started = x.warmup_started_at
        if started is None:
            age = age or "new"
        else:
            days = (datetime.now(timezone.utc) - (started if started.tzinfo else started.replace(tzinfo=timezone.utc))).days
            age = age or ("new" if days < 14 else "warming" if days < 60 else "established")
    age = age or "new"
    table = {"new": (20, 10, 20), "warming": (40, 20, 40), "established": (80, 30, 60)}
    action, invites, messages = table[age]
    action, invites, messages = min(action, DAILY_ACTION_CEILING), min(invites, INVITE_CEILING), min(messages, MESSAGE_CEILING)
    return {"accountAge": age, "dailyActionLimit": action, "dailyConnectionLimit": invites, "dailyMessageLimit": messages,
            "ceilings": {"dailyActions": DAILY_ACTION_CEILING, "dailyInvites": INVITE_CEILING, "dailyMessages": MESSAGE_CEILING, "weeklyInvites": WEEKLY_INVITE_CEILING},
            "why": ["Synex also ramps any account up from 5 actions a day, adding 5 each day, so a new account starts slowly whatever the limit says.",
                    f"{invites} invites a day on five working days is {invites * 5} a week, inside the {WEEKLY_INVITE_CEILING} weekly ceiling.",
                    "These are starting points. Raise them only while replies stay healthy and the account has no warnings."]}


# =========================================================================================== write tools ========
class LeadItem(Args):
    first_name: str = Field("", max_length=80)
    last_name: str = Field("", max_length=80)
    company: str = Field("", max_length=120)
    job_title: str = Field("", max_length=120)
    linkedin_url: str = Field("", max_length=300)


class CreateLeadList(Args):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(None, max_length=300)
    leads: list[LeadItem] = Field(min_length=1, max_length=100, description="The leads the user gave you. Never invent people.")

    @field_validator("leads")
    @classmethod
    def _each_identifiable(cls, leads: list[LeadItem]) -> list[LeadItem]:
        for lead in leads:
            if not (lead.first_name or lead.last_name or lead.linkedin_url):
                raise ValueError("every lead needs a name or a LinkedIn URL")
        return leads


def _propose_list(ctx: ToolContext, a: CreateLeadList) -> Plan:
    return Plan(f'Create the list "{a.name}" with {len(a.leads)} lead{"s" if len(a.leads) != 1 else ""}.',
                [f'A new lead list named "{a.name}".', f"{len(a.leads)} lead{'s' if len(a.leads) != 1 else ''} added to it. Anyone already in your workspace is matched, not duplicated.",
                 "Nothing is sent to anyone."])


def _apply_list(ctx: ToolContext, a: CreateLeadList) -> dict:
    created = lists_router._create(LeadListIn(name=a.name, description=a.description), ctx.db, ctx.workspace)
    counts = leads_router._bulk_create(BulkImportIn(leads=[LeadIn(**l.model_dump()) for l in a.leads], list_ids=[created["id"]]), ctx.db, ctx.workspace)
    return {"listId": created["id"], **counts}


class CreateTemplate(Args):
    name: str = Field(min_length=1, max_length=100)
    category: Literal["connection", "first_message", "follow_up", "reply"] = "first_message"
    body: str = Field(min_length=1, max_length=3000)


def _check_body(category: str | None, body: str | None) -> None:
    if category == "connection" and body is not None and len(body) > 300:
        raise ToolError("A connection note can be 300 characters at most on LinkedIn. This one is %d." % len(body))


def _propose_template(ctx: ToolContext, a: CreateTemplate) -> Plan:
    _check_body(a.category, a.body)
    return Plan(f'Save a new {a.category.replace("_", " ")} template called "{a.name}".',
                [f'A new template named "{a.name}" ({a.category.replace("_", " ")}).', f"Text: {a.body[:300]}"])


def _apply_template(ctx: ToolContext, a: CreateTemplate) -> dict:
    out = templates_router._create(TemplateIn(name=a.name, category=a.category, body=a.body), ctx.db, ctx.workspace)
    return {"templateId": out["id"]}


class UpdateTemplate(Args):
    template_id: str
    name: str | None = Field(None, min_length=1, max_length=100)
    category: Literal["connection", "first_message", "follow_up", "reply"] | None = None
    body: str | None = Field(None, min_length=1, max_length=3000)


def _propose_template_edit(ctx: ToolContext, a: UpdateTemplate) -> Plan:
    t = _owned(ctx, models.Template, a.template_id, "template")
    if a.name is None and a.category is None and a.body is None:
        raise ToolError("Say what to change: the name, the category or the text.")
    _check_body(a.category or t.category, a.body if a.body is not None else t.body)
    changes = []
    if a.name is not None and a.name != t.name:
        changes.append(f'Rename "{t.name}" to "{a.name}".')
    if a.category is not None and a.category != t.category:
        changes.append(f"Change the category from {t.category.replace('_', ' ')} to {a.category.replace('_', ' ')}.")
    if a.body is not None and a.body != t.body:
        changes.append(f"Replace the text ({len(t.body)} to {len(a.body)} characters). New text: {a.body[:300]}")
    if not changes:
        raise ToolError("That is already how the template is. Nothing to change.")
    return Plan(f'Edit the template "{t.name}".', changes)


def _apply_template_edit(ctx: ToolContext, a: UpdateTemplate) -> dict:
    data = a.model_dump(exclude_none=True, exclude={"template_id"})
    templates_router._update(a.template_id, TemplateUpdateIn(**data), ctx.db, ctx.workspace)
    return {"templateId": a.template_id}


class StepArg(Args):
    type: Literal["connection_request", "message", "follow_up", "wait", "profile_visit", "follow"]
    message: str | None = Field(None, max_length=1500)
    delay_hours: int | None = Field(None, ge=0, le=24 * 30, description="For wait steps.")


class CreateCampaignDraft(Args):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(None, max_length=300)
    steps: list[StepArg] = Field(min_length=1, max_length=12)
    lead_list_id: str | None = None
    account_id: str | None = None
    daily_connection_limit: int | None = Field(None, ge=0, description=f"0 pauses invites. Hard ceiling {INVITE_CEILING} a day.")
    daily_message_limit: int | None = Field(None, ge=0, description=f"0 pauses messages. Hard ceiling {MESSAGE_CEILING} a day.")
    timezone: str | None = Field(None, max_length=60, description="IANA name such as Asia/Kolkata.")
    start_hour: int | None = Field(None, ge=0, le=23)
    end_hour: int | None = Field(None, ge=1, le=24)
    working_days: list[int] | None = Field(None, description="0=Sunday to 6=Saturday.")
    stop_when_replied: bool | None = None


def _campaign_input(ctx: ToolContext, a: CreateCampaignDraft) -> CampaignIn:
    if a.lead_list_id:
        _owned(ctx, models.LeadList, a.lead_list_id, "lead list")
    if a.account_id:
        _owned(ctx, models.LinkedInAccount, a.account_id, "sender account")
    if a.timezone:
        try:
            ZoneInfo(a.timezone)
        except Exception:
            raise ToolError(f"{a.timezone} is not a timezone name I recognise. Use one like Asia/Kolkata or America/New_York.")
    if a.start_hour is not None and a.end_hour is not None and a.start_hour >= a.end_hour:
        raise ToolError("The start hour must be before the end hour.")
    if a.working_days is not None and (not a.working_days or any(d < 0 or d > 6 for d in a.working_days)):
        raise ToolError("Working days must be numbers from 0 (Sunday) to 6 (Saturday).")
    steps = [StepIn(type=s.type, order=i, message=s.message, delay_hours=(s.delay_hours if s.delay_hours is not None else 48) if s.type == "wait" else None)
             for i, s in enumerate(a.steps)]
    steps.append(StepIn(type="end", order=len(steps)))
    fields = a.model_dump(exclude={"steps"}, exclude_none=True)
    return _parse(CampaignIn, **fields, steps=steps)  # the ceilings are enforced here, naming the ceiling


def _propose_campaign(ctx: ToolContext, a: CreateCampaignDraft) -> Plan:
    _campaign_input(ctx, a)
    kinds = ", ".join(s.type.replace("_", " ") for s in a.steps)
    changes = [f'A new campaign named "{a.name}", saved as a draft. It will not start.', f"Sequence: {kinds}."]
    empty = [s for s in a.steps if s.type in ("message", "follow_up") and not (s.message or "").strip()]
    if empty:
        changes.append(f"{len(empty)} message step{'s' if len(empty) != 1 else ''} are blank for you to write.")
    if a.daily_connection_limit is not None:
        changes.append(f"Up to {a.daily_connection_limit} connection requests a day.")
    if a.daily_message_limit is not None:
        changes.append(f"Up to {a.daily_message_limit} messages a day.")
    if a.lead_list_id:
        changes.append(f'Uses the list "{ctx.db.get(models.LeadList, a.lead_list_id).name}".')
    return Plan(f'Create the draft campaign "{a.name}".', changes)


def _apply_campaign(ctx: ToolContext, a: CreateCampaignDraft) -> dict:
    out = campaigns_router._create(_campaign_input(ctx, a), ctx.db, ctx.workspace)
    return {"campaignId": out["id"], "status": out["status"]}


class SetCampaignState(Args):
    campaign_id: str
    action: Literal["pause", "resume"]


def _propose_campaign_state(ctx: ToolContext, a: SetCampaignState) -> Plan:
    c = _owned(ctx, models.Campaign, a.campaign_id, "campaign")
    if a.action == "pause":
        if c.status != "active":
            raise ToolError(f'"{c.name}" is {c.status}, not running, so there is nothing to pause.')
        return Plan(f'Pause the campaign "{c.name}".', ["No new actions are sent for it until it is resumed.", "Leads keep their place in the sequence."])
    if c.status == "draft" or c.launched_at is None:
        raise ToolError("Launching a campaign for the first time is not available through the assistant yet. Launch it from the campaign page.")
    if c.status != "paused":
        raise ToolError(f'"{c.name}" is {c.status}, so it cannot be resumed.')
    return Plan(f'Resume the campaign "{c.name}".', ["It starts sending again within its daily limits and working hours.", "Synex re-checks it can run (account connected, leads, messages) before it does."])


def _apply_campaign_state(ctx: ToolContext, a: SetCampaignState) -> dict:
    _owned(ctx, models.Campaign, a.campaign_id, "campaign")
    out = campaigns_router._update(a.campaign_id, CampaignUpdateIn(status="paused" if a.action == "pause" else "active"), ctx.db, ctx.workspace)
    return {"campaignId": a.campaign_id, "status": out["status"]}


class SetAccountState(Args):
    account_id: str
    action: Literal["pause", "resume"]


def _propose_account_state(ctx: ToolContext, a: SetAccountState) -> Plan:
    x = _owned(ctx, models.LinkedInAccount, a.account_id, "sender account")
    if a.action == "pause":
        if x.status == "paused":
            raise ToolError(f"{x.name} is already paused.")
        return Plan(f"Pause the sender account {x.name}.", ["It sends nothing from every campaign until resumed."])
    if x.status != "paused":
        raise ToolError(f"{x.name} is not paused.")
    return Plan(f"Resume the sender account {x.name}.", ["It can send again within its limits.", "If its LinkedIn session has expired it stays unavailable until an admin reconnects it."])


def _apply_account_state(ctx: ToolContext, a: SetAccountState) -> dict:
    accounts_router.update_account(a.account_id, AccountPatch.model_validate({"paused": a.action == "pause"}), ctx.db, ctx.workspace, ctx.actor)
    return {"accountId": a.account_id, "paused": a.action == "pause"}


class SetDailyLimits(Args):
    target: Literal["account", "campaign"]
    id: str
    daily_action_limit: int | None = Field(None, ge=0, description=f"Accounts only. 0 stops the account. Hard ceiling {DAILY_ACTION_CEILING} a day.")
    daily_connection_limit: int | None = Field(None, ge=0, description=f"Campaigns only. 0 pauses invites. Hard ceiling {INVITE_CEILING} a day.")
    daily_message_limit: int | None = Field(None, ge=0, description=f"Campaigns only. 0 pauses messages. Hard ceiling {MESSAGE_CEILING} a day.")


def _validate_limits(ctx: ToolContext, a: SetDailyLimits):
    """The same checks the API makes, so the ceilings hold through the assistant too (and a 0 stays a 0)."""
    if a.target == "account":
        if ROLE_RANK.get(ctx.role, 0) < ROLE_RANK["admin"]:
            raise ToolError(f"Your role ({ctx.role}) cannot change a sender account's limits. It needs a workspace admin.")
        if a.daily_connection_limit is not None or a.daily_message_limit is not None:
            raise ToolError("Accounts have one daily action limit. Connection and message limits belong to a campaign.")
        if a.daily_action_limit is None:
            raise ToolError("Say which limit to set: the account's daily action limit.")
        if a.daily_action_limit > DAILY_ACTION_CEILING:
            raise ToolError(f"{a.daily_action_limit} is above the hard ceiling of {DAILY_ACTION_CEILING} actions a day per account. Choose {DAILY_ACTION_CEILING} or less (0 stops the account).")
        return AccountPatch.model_validate({"dailyActionLimit": a.daily_action_limit})
    if a.daily_action_limit is not None:
        raise ToolError("A campaign has connection and message limits. The daily action limit belongs to the sender account.")
    if a.daily_connection_limit is None and a.daily_message_limit is None:
        raise ToolError("Say which limit to set: connection requests or messages.")
    if a.daily_connection_limit is not None and a.daily_connection_limit > INVITE_CEILING:
        raise ToolError(f"{a.daily_connection_limit} is above the hard ceiling of {INVITE_CEILING} connection requests a day. Choose {INVITE_CEILING} or less (0 pauses them).")
    if a.daily_message_limit is not None and a.daily_message_limit > MESSAGE_CEILING:
        raise ToolError(f"{a.daily_message_limit} is above the hard ceiling of {MESSAGE_CEILING} messages a day. Choose {MESSAGE_CEILING} or less (0 pauses them).")
    data = {k: v for k, v in (("dailyConnectionLimit", a.daily_connection_limit), ("dailyMessageLimit", a.daily_message_limit)) if v is not None}
    return _parse(CampaignUpdateIn, **data)


def _propose_limits(ctx: ToolContext, a: SetDailyLimits) -> Plan:
    payload = _validate_limits(ctx, a)
    if a.target == "account":
        x = _owned(ctx, models.LinkedInAccount, a.id, "sender account")
        now_limit = engine.configured_daily_limit(x)
        extra = ["0 stops this account completely."] if a.daily_action_limit == 0 else ["New accounts still ramp up from 5 actions a day whatever this is set to."]
        return Plan(f"Set {x.name}'s daily action limit to {a.daily_action_limit}.", [f"Daily action limit: {now_limit} now, {a.daily_action_limit} after.", *extra])
    c = _owned(ctx, models.Campaign, a.id, "campaign")
    changes = []
    if a.daily_connection_limit is not None:
        changes.append(f"Connection requests a day: {engine.campaign_type_limit(c, 'send_invite')} now, {a.daily_connection_limit} after.")
        if a.daily_connection_limit * 7 > WEEKLY_INVITE_CEILING:
            changes.append(f"Note: an account can send {WEEKLY_INVITE_CEILING} connection requests a week at most, so sending stops earlier in the week at this rate.")
    if a.daily_message_limit is not None:
        changes.append(f"Messages a day: {engine.campaign_type_limit(c, 'send_message')} now, {a.daily_message_limit} after.")
    return Plan(f'Change the daily limits on "{c.name}".', changes)


def _apply_limits(ctx: ToolContext, a: SetDailyLimits) -> dict:
    payload = _validate_limits(ctx, a)
    if a.target == "account":
        _owned(ctx, models.LinkedInAccount, a.id, "sender account")
        accounts_router.update_account(a.id, payload, ctx.db, ctx.workspace, ctx.actor)
        return {"accountId": a.id, "dailyActionLimit": a.daily_action_limit}
    _owned(ctx, models.Campaign, a.id, "campaign")
    campaigns_router._update(a.id, payload, ctx.db, ctx.workspace)
    return {"campaignId": a.id}


# =========================================================================================== registration =======
def _read(name, description, args, run, role="member"):
    register(Tool(name, description, args, "read", role, run=run))


_read("get_dashboard_summary", "Headline numbers for the workspace: leads, active campaigns, invites, replies, rates, accounts needing attention.", NoArgs, _dashboard)
_read("search_campaigns", "List or search campaigns by name and status.", SearchCampaigns, _search_campaigns)
_read("get_campaign", "One campaign's steps, limits, schedule and list.", CampaignId, _get_campaign)
_read("explain_campaign_status", "Explain in plain words why a campaign is paused, stopped or not sending, and what to do.", CampaignId, _explain_campaign)
_read("search_leads", "Search leads by name, company or job title, optionally by status or list.", SearchLeads, _search_leads)
_read("get_lead", "One lead's stored details and history (events and recent messages).", LeadId, _get_lead)
_read("list_lead_lists", "All lead lists with their sizes.", NoArgs, _list_lists)
_read("list_templates", "Message templates, optionally filtered by name or category.", SearchTemplates, _list_templates)
_read("list_sender_accounts", "Sender accounts with status, health and daily limits.", NoArgs, _list_accounts)
_read("explain_account_status", "Explain why a sender account is not sending or needs reconnecting, and what to do.", AccountId, _explain_account)

register(Tool("draft_message", "Prepare a connection note, message or follow-up for the user to edit. If you write the text yourself, pass it in `text`. It is only shown to the user; it is never saved or sent.",
              DraftMessage, "draft", "member", run=_draft))
register(Tool("propose_sequence", "Outline a campaign sequence for a goal (steps, timing, safe limits). Does not create anything.", ProposeSequence, "draft", "member", run=_propose_sequence))
register(Tool("suggest_limits", "Recommend safe starting daily limits for a new or existing sender account.", SuggestLimits, "draft", "member", run=_suggest_limits))

register(Tool("create_lead_list", "Prepare a new lead list from leads the user gave you. Needs the user's confirmation.", CreateLeadList, "write", "manager", propose=_propose_list, apply=_apply_list))
register(Tool("create_template", "Prepare a new message template. Needs the user's confirmation.", CreateTemplate, "write", "manager", propose=_propose_template, apply=_apply_template))
register(Tool("update_template", "Prepare an edit to an existing template. Needs the user's confirmation.", UpdateTemplate, "write", "manager", propose=_propose_template_edit, apply=_apply_template_edit))
register(Tool("create_campaign_draft", "Prepare a new DRAFT campaign with steps and settings. It never launches. Needs the user's confirmation.", CreateCampaignDraft, "write", "manager", propose=_propose_campaign, apply=_apply_campaign))
register(Tool("set_campaign_state", "Prepare pausing a running campaign or resuming a paused one. Needs the user's confirmation.", SetCampaignState, "write", "manager", propose=_propose_campaign_state, apply=_apply_campaign_state))
register(Tool("set_account_state", "Prepare pausing or resuming a sender account. Needs the user's confirmation.", SetAccountState, "write", "admin", propose=_propose_account_state, apply=_apply_account_state))
register(Tool("set_daily_limits", "Prepare a change to a sender account's or campaign's daily limits, within the hard ceilings. Needs the user's confirmation.", SetDailyLimits, "write", "manager", propose=_propose_limits, apply=_apply_limits))
