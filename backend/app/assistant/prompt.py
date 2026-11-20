"""The system prompt and the Settings message that configures a Deepgram agent session."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .. import models
from ..config import DAILY_ACTION_CEILING, DAILY_TYPE_CEILINGS, WEEKLY_INVITE_CEILING
from ..serializers import account_display_status
from .config import assistant_config
from .registry import function_definitions

GREETING = "Hi, I'm the Synex assistant. What would you like to do?"


def clean_page(db: Session, workspace_id: str, page: dict | None) -> dict:
    """What the user is looking at, with every id checked against the workspace. Unknown ids are dropped."""
    page = page if isinstance(page, dict) else {}
    out: dict = {"path": str(page.get("path", ""))[:200]}
    cid, lid = page.get("campaignId"), page.get("leadId")
    if isinstance(cid, str):
        c = db.get(models.Campaign, cid)
        if c and c.user_id == workspace_id:
            out["campaignId"], out["campaignName"] = c.id, c.name
    if isinstance(lid, str):
        l = db.get(models.Lead, lid)
        if l and l.user_id == workspace_id:
            out["leadId"], out["leadName"] = l.id, f"{l.first_name} {l.last_name}".strip() or "Unnamed lead"
    if isinstance(page.get("field"), str):
        out["field"] = page["field"][:60]
    return out


def workspace_snapshot(db: Session, workspace: models.User) -> str:
    """Names and counts only. No emails, phone numbers, tokens, cookies, proxies or message text."""
    campaigns = db.query(models.Campaign).filter_by(user_id=workspace.id).order_by(models.Campaign.created_at.desc()).all()
    lists = db.query(models.LeadList).filter_by(user_id=workspace.id).order_by(models.LeadList.created_at.desc()).all()
    accounts = db.query(models.LinkedInAccount).filter_by(user_id=workspace.id).all()
    templates = db.query(models.Template).filter_by(user_id=workspace.id).count()
    leads = db.query(models.Lead).filter_by(user_id=workspace.id).count()
    by_status: dict[str, int] = {}
    for c in campaigns:
        by_status[c.status] = by_status.get(c.status, 0) + 1
    lines = [f"Leads: {leads}. Templates: {templates}. Lead lists: {len(lists)}. Campaigns: {len(campaigns)} ({', '.join(f'{n} {s}' for s, n in by_status.items()) or 'none'}).",
             "Campaigns: " + (", ".join(f'"{c.name}" ({c.status})' for c in campaigns[:8]) or "none") + ("." if len(campaigns) <= 8 else ", and more."),
             "Lead lists: " + (", ".join(f'"{l.name}"' for l in lists[:8]) or "none") + ("." if len(lists) <= 8 else ", and more."),
             "Sender accounts: " + (", ".join(f'"{a.name}" ({account_display_status(a)})' for a in accounts[:6]) or "none") + "."]
    return "\n".join(lines)


def build_prompt(db: Session, workspace: models.User, actor: models.User, role: str, page: dict, language: str) -> str:
    first = (actor.full_name or "").split(" ")[0] or "there"
    where = page.get("path") or "an unknown page"
    focus = []
    if page.get("campaignName"):
        focus.append(f'the campaign "{page["campaignName"]}" (id {page["campaignId"]})')
    if page.get("leadName"):
        focus.append(f'the lead {page["leadName"]} (id {page["leadId"]})')
    if page.get("field"):
        focus.append(f'a text field called "{page["field"]}"')
    looking = ("They are looking at " + " and ".join(focus) + ".") if focus else "They are not looking at one specific record."
    lang = "Indian English; keep wording simple and avoid idioms" if language == "en-IN" else "English"
    return f"""You are the Synex assistant, built into Synex, a LinkedIn outreach app. You help {first} plan, draft and set up outreach by voice or text. Speak {lang}.

# Who you are talking to
Name: {first}. Their role in this workspace: {role} (admin > manager > member). They are on {where}. {looking}

# Their workspace right now (names and counts only)
{workspace_snapshot(db, workspace)}

# How you work
- Use your tools to look things up. Never guess numbers, names or statuses; if a tool does not answer it, say you do not know.
- Reading and drafting are free. Anything that changes data is a PROPOSAL: the tool shows the user a confirmation card and applies nothing. Say what you prepared in one sentence and ask them to press Confirm on the card. A spoken "yes" does not apply anything; only the Confirm button does. Never say a change is done until they confirm it.
- When asked for message copy, write the text yourself and pass it to draft_message in `text` so it appears with an Insert button. Use only facts the user or the lead's stored data gave you; never invent facts about a person. Drafts are for the user to edit; you cannot send them.
- When they are editing a campaign (an id is given above) and ask you to build it, ask what they sell or want, who it is for and the tone, then write the finished message for every step yourself and call set_campaign_sequence with the whole sequence, so the campaign is ready to review. A good default for people who are not connected yet is a connection request, a wait of 2 days, a message, a wait of 3 days, a follow-up. If the campaign's lead list is all existing connections, never include a connection request: start with a message, then a wait of 3 days and a follow-up. Use get_campaign to see the list before you write. You cannot launch: tell them to check the Review step and launch it themselves.
- Keep answers short and natural for speech: one to three sentences, no lists read aloud, no markdown, no emoji. Say numbers plainly. If something needs detail, say you have put it on screen.
- Ask one short question when you need a missing detail. Do not ask for permission to look things up.
- If a tool refuses (permission, ceiling, not found), tell the user the reason in plain words and what they can do instead.

# Safety limits you must respect and explain
- Hard ceilings per sender account: {DAILY_ACTION_CEILING} actions a day in total; {DAILY_TYPE_CEILINGS['send_invite']} connection requests, {DAILY_TYPE_CEILINGS['send_message']} messages, {DAILY_TYPE_CEILINGS['visit_profile']} profile visits and {DAILY_TYPE_CEILINGS['follow_profile']} follows a day; {WEEKLY_INVITE_CEILING} connection requests a week. Nothing can raise them. A limit of 0 means stopped, never unlimited. New accounts ramp up slowly from 5 actions a day.
- You act only with the signed-in user's permissions. Do not try to work around a refusal.

# What you cannot do yet (say so plainly if asked)
You cannot send messages, reply in the inbox, launch a campaign for the first time, delete anything, or import leads from LinkedIn searches. You can draft, propose, create drafts and lists the user gives you, pause or resume, and adjust limits within the ceilings. You never see passwords, cookies or tokens and cannot sign in to LinkedIn.

# Privacy
Everything said and typed here is processed by Deepgram and the language model it uses. Do not ask for passwords or other secrets. If the user shares one, tell them not to."""


def build_settings(prompt: str, mode: str, language: str) -> dict:
    cfg = assistant_config
    think: dict = {
        "provider": {"type": cfg.assistant_llm_provider, "model": cfg.assistant_llm_model},
        "prompt": prompt,
        # No `endpoint`: with none, Deepgram asks the client (our relay) to run each function, and our relay
        # runs it on the server through the registry. Nothing runs in the browser.
        "functions": function_definitions(),
    }
    agent: dict = {
        "listen": {"provider": {"type": "deepgram", "version": "v1", "model": cfg.assistant_stt_model, "language": language, "smart_format": True}},
        "think": think,
        "speak": {"provider": {"type": "deepgram", "model": cfg.assistant_voice}},
    }
    if mode == "voice":
        agent["greeting"] = GREETING
    return {
        "type": "Settings",
        "tags": ["synex-assistant"],
        "mip_opt_out": True,  # keep this workspace's data out of Deepgram's model-improvement programme
        "audio": {
            "input": {"encoding": "linear16", "sample_rate": 16000},
            "output": {"encoding": "linear16", "sample_rate": 24000, "container": "none"},
        },
        "agent": agent,
    }
