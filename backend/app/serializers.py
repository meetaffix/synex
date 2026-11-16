"""Convert ORM models into the camelCase JSON shapes the frontend expects."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import campaign_settings, models

# An account is shown "connected" only while its extension heartbeat is fresh.
# Keep in sync with engine.AGENT_STALE_MINUTES.
AGENT_STALE_MINUTES = 3

# Lead statuses grouped by how far a lead has progressed through outreach.
# Used to derive campaign stats from real lead state (no stored counters).
INVITED_STATES = {"contacted", "connected", "replied", "interested", "not_interested"}
CONNECTED_STATES = {"connected", "replied", "interested", "not_interested"}
REPLIED_STATES = {"replied", "interested", "not_interested"}


def _iso(dt: datetime | None) -> str | None:
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat() if dt else None


# --------------------------------- User ----------------------------------
def user_out(u: models.User) -> dict:
    # Admins bypass all subscription gating: their effective plan is the top
    # tier, so no limits apply and the frontend never shows upgrade prompts.
    is_admin = (u.role or "").strip().lower() == "admin"
    return {
        "id": u.id,
        "email": u.email,
        "fullName": u.full_name,
        "avatarUrl": u.avatar_url,
        "company": u.company,
        "role": u.role,
        "plan": "scale" if is_admin else u.plan,
        "isAdmin": is_admin,
        "createdAt": _iso(u.created_at),
    }


# ------------------------------- Accounts --------------------------------
def account_display_status(a: models.LinkedInAccount) -> str:
    """Map lifecycle + liveness signal to a frontend status."""
    if a.status == "paused":
        return "paused"
    if a.session_status:
        return a.session_status  # connected | needs_reconnect | restricted | disconnected
    # Cloud mode: status derives from the stored-session health.
    if getattr(a, "execution_mode", "extension") == "cloud":
        cs = getattr(a, "cloud_status", None)
        if cs == "active":
            return "connected"
        if cs == "cookie_expired":
            return "session_expired"
        if cs == "proxy_error":
            return "proxy_error"
        return "pending"
    # Extension mode: status derives from heartbeat freshness.
    if a.status == "pending" or not a.agent_token:
        return "pending"
    last = a.agent_last_seen_at
    if last is not None:
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - last < timedelta(minutes=AGENT_STALE_MINUTES):
            return "connected"
    return "disconnected"


def account_out(a: models.LinkedInAccount) -> dict:
    from .engine import effective_daily_limit  # local import avoids load-order coupling

    now = datetime.now(timezone.utc)
    effective = effective_daily_limit(a, now)
    return {
        "id": a.id,
        "name": a.name,
        "email": a.email,
        "headline": a.headline,
        "linkedinUrl": a.linkedin_url,
        "status": account_display_status(a),
        "hasToken": bool(a.agent_token),
        "agentLastSeenAt": _iso(a.agent_last_seen_at),
        "dailyActionLimit": a.daily_action_limit,
        "effectiveDailyLimit": effective,
        "warmingUp": bool(a.daily_action_limit) and effective < a.daily_action_limit,
        "dailyActionsUsed": a.daily_actions_used,
        "messagesSent": a.messages_sent,
        "connectionsSent": a.connections_sent,
        "lastSyncAt": _iso(a.last_sync_at),
        "createdAt": _iso(a.created_at),
        # Cloud execution fields.
        "executionMode": getattr(a, "execution_mode", "extension") or "extension",
        "cloudStatus": getattr(a, "cloud_status", None),
        "hasSession": bool(getattr(a, "li_at_encrypted", None)),
        "cookieHarvestedAt": _iso(getattr(a, "cookie_harvested_at", None)),
    }


# --------------------------------- Leads ---------------------------------
def lead_out(lead: models.Lead) -> dict:
    return {
        "id": lead.id,
        "firstName": lead.first_name,
        "lastName": lead.last_name,
        "company": lead.company,
        "jobTitle": lead.job_title,
        "headline": lead.headline,
        "linkedinUrl": lead.linkedin_url,
        "email": lead.email,
        "phone": lead.phone,
        "location": lead.location,
        "industry": lead.industry,
        "timezone": lead.timezone,
        "connectedAt": _iso(lead.connected_at),
        "mutualConnections": lead.mutual_connections,
        "tags": lead.tags or [],
        "variables": lead.variables or {},
        "source": lead.source,
        "status": lead.status,
        "notes": lead.notes,
        "listIds": [l.id for l in lead.lists],
        "campaignId": lead.campaign_id,
        "avatarUrl": lead.avatar_url,
        "createdAt": _iso(lead.created_at),
        "updatedAt": _iso(lead.updated_at),
    }


def lead_list_out(ll: models.LeadList) -> dict:
    return {
        "id": ll.id,
        "name": ll.name,
        "description": ll.description,
        "color": ll.color,
        "leadCount": len(ll.leads),
        "createdAt": _iso(ll.created_at),
    }


# ------------------------------- Campaigns -------------------------------
def step_out(s: models.CampaignStep) -> dict:
    return {
        "id": s.id,
        "type": s.type,
        "order": s.order,
        "message": s.message,
        "delayHours": s.delay_hours,
        "parentStepId": s.parent_step_id,
        "branchCondition": s.branch_condition,
        "aiConfig": s.ai_config,
    }


def campaign_stats(c: models.Campaign) -> dict:
    leads = c.lead_list.leads if c.lead_list else []
    invited = sum(1 for l in leads if l.status in INVITED_STATES)
    connected = sum(1 for l in leads if l.status in CONNECTED_STATES)
    replied = sum(1 for l in leads if l.status in REPLIED_STATES)
    messages_sent = sum(
        1
        for convo in c.conversations
        for m in convo.messages
        if m.direction == "outbound"
    )
    return {
        "totalLeads": len(leads),
        "invitesSent": invited,
        "connected": connected,
        "replied": replied,
        "interested": sum(1 for l in leads if l.status == "interested"),
        "messagesSent": messages_sent,
        "acceptanceRate": round(connected / invited * 100, 1) if invited else 0.0,
        "replyRate": round(replied / invited * 100, 1) if invited else 0.0,
    }


def campaign_out(c: models.Campaign) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "description": c.description,
        "status": c.status,
        "accountId": c.account_id,
        "accountIds": c.account_ids or [],
        "accountName": c.account.name if c.account else "",
        "accountStatus": account_display_status(c.account) if c.account else None,
        "leadListId": c.lead_list_id,
        "leadListName": c.lead_list.name if c.lead_list else "",
        "dailyConnectionLimit": c.daily_connection_limit,
        "dailyMessageLimit": c.daily_message_limit,
        "schedule": {
            "timezone": c.timezone,
            "days": c.working_days or [],
            "startHour": c.start_hour,
            "endHour": c.end_hour,
        },
        "settings": {
            "randomDelay": bool(c.random_delay),
            "stopWhenReplied": bool(c.stop_when_replied),
            "stopWhenAccepted": bool(c.stop_when_accepted),
            "aiPersonalization": bool(c.ai_personalization),
            "pauseOnFailure": bool(c.pause_on_failure),
        },
        "audienceSource": c.audience_source,
        "weekSchedule": c.week_schedule,
        "exclusions": {**campaign_settings.DEFAULT_EXCLUSIONS, **(c.exclusions or {})},
        "allocation": c.allocation or {},
        "aiContext": c.ai_context or {},
        "sequenceMode": c.sequence_mode or "classic",
        "graph": c.graph,
        "launchSummary": c.launch_summary,
        "steps": [step_out(s) for s in sorted(c.steps, key=lambda x: x.order)],
        "stats": campaign_stats(c),
        "createdAt": _iso(c.created_at),
        "updatedAt": _iso(c.updated_at),
    }


# ----------------------------- Conversations -----------------------------
def conversation_out(c: models.Conversation) -> dict:
    lead = c.lead
    name = f"{lead.first_name} {lead.last_name}".strip() if lead else ""
    return {
        "id": c.id,
        "leadId": c.lead_id,
        "leadName": name or "Unknown",
        "leadTitle": (lead.job_title or lead.headline or "") if lead else "",
        "leadCompany": lead.company if lead else "",
        "linkedinUrl": lead.linkedin_url if lead else None,
        "avatarUrl": lead.avatar_url if lead else None,
        "accountId": c.account_id,
        "campaignId": c.campaign_id,
        "campaignName": c.campaign.name if c.campaign else None,
        "lastMessagePreview": c.last_message_preview,
        "lastMessageAt": _iso(c.last_message_at),
        "unread": c.unread,
        "status": c.status,
    }


def message_out(m: models.Message) -> dict:
    return {
        "id": m.id,
        "conversationId": m.conversation_id,
        "direction": m.direction,
        "body": m.body,
        "sentAt": _iso(m.sent_at),
        "read": m.read,
        "deliveryStatus": m.delivery_status or "sent",
        "deliveryError": m.delivery_error,
    }


# ------------------------------ Import jobs ------------------------------
def import_job_out(j: models.ImportJob) -> dict:
    return {
        "id": j.id,
        "source": j.source,
        "status": j.status,
        "createdCount": j.created_count or 0,
        "fetchedCount": j.fetched_count or 0,
        "totalCount": j.total_count,
        "detail": j.detail,
        "createdAt": _iso(j.created_at),
    }


# ------------------------------- Templates -------------------------------
def template_out(t: models.Template) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "category": t.category,
        "body": t.body,
        "usageCount": t.usage_count,
        "replyRate": t.reply_rate,
        "shortcut": t.shortcut,
        "createdAt": _iso(t.created_at),
        "updatedAt": _iso(t.updated_at),
    }
