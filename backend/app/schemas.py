"""Request body schemas (camelCase in, validated)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator
from pydantic.alias_generators import to_camel

from .config import DAILY_TYPE_CEILINGS
from .linkedin_session.identity import validate_timezone


class CamelIn(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


def _campaign_limit(name: str, ttype: str):
    """A campaign's daily limit: 0 pauses that action; above the hard ceiling is refused, naming the ceiling."""
    label = {"send_invite": "connection requests", "send_message": "messages"}[ttype]

    def check(cls, value: int | None) -> int | None:
        if value is None:
            return None
        ceiling = DAILY_TYPE_CEILINGS[ttype]
        if value < 0 or value > ceiling:
            raise ValueError(f"Daily {label} must be 0 to {ceiling}: {ceiling} a day is the hard ceiling per account, and 0 pauses them.")
        return value

    return field_validator(name)(check)


# --------------------------------- Auth ----------------------------------
class LoginIn(CamelIn):
    email: EmailStr
    password: str


class RegisterIn(CamelIn):
    full_name: str
    email: EmailStr
    password: str


class PasswordResetIn(CamelIn):
    """One endpoint, two phases: an email-only body requests a reset link;
    a token+password body confirms the new password."""
    email: EmailStr | None = None
    token: str | None = None
    password: str | None = None


class ProfileUpdateIn(CamelIn):
    full_name: str | None = None
    email: EmailStr | None = None
    company: str | None = None
    role: str | None = None
    avatar_url: str | None = None


# --------------------------------- Leads ---------------------------------
RESERVED_VARIABLES = {"first_name", "last_name", "name", "full_name", "company", "job_title", "designation", "location", "headline", "industry"}


def check_variables(value: dict | None) -> dict | None:
    """Custom variables: a short name of letters, digits and underscores, never one Synex already fills, and a short value."""
    if value is None:
        return None
    import re
    if len(value) > 20:
        raise ValueError("A lead can have at most 20 custom variables.")
    out = {}
    for name, text in value.items():
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,39}", str(name)):
            raise ValueError(f"'{name}' is not a valid variable name. Use letters, digits and underscores, starting with a letter.")
        if str(name).lower() in RESERVED_VARIABLES or str(name).lower().startswith(("linkedin_", "sender_")):
            raise ValueError(f"'{name}' is already filled in by Synex. Choose another name.")
        if not isinstance(text, str) or len(text) > 500:
            raise ValueError(f"The value of '{name}' must be text of at most 500 characters.")
        out[str(name)] = text
    return out


class LeadIn(CamelIn):
    first_name: str | None = ""
    last_name: str | None = ""
    company: str | None = ""
    job_title: str | None = ""
    headline: str | None = None
    linkedin_url: str | None = ""
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    industry: str | None = None
    timezone: str | None = None  # IANA name; overrides the campaign timezone for working hours
    tags: list[str] | None = None
    status: str | None = "new"
    notes: str | None = None
    list_ids: list[str] | None = None
    variables: dict | None = None

    @field_validator("variables")
    @classmethod
    def _variables(cls, value):
        return check_variables(value)

    @field_validator("timezone")
    @classmethod
    def _timezone(cls, value: str | None) -> str | None:
        return validate_timezone(value.strip()) if value and value.strip() else None


class LeadUpdateIn(CamelIn):
    first_name: str | None = None
    last_name: str | None = None
    company: str | None = None
    job_title: str | None = None
    headline: str | None = None
    linkedin_url: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    industry: str | None = None
    timezone: str | None = None
    tags: list[str] | None = None
    status: str | None = None
    notes: str | None = None
    list_ids: list[str] | None = None
    variables: dict | None = None

    @field_validator("variables")
    @classmethod
    def _variables(cls, value):
        return check_variables(value)

    @field_validator("timezone")
    @classmethod
    def _timezone(cls, value: str | None) -> str | None:
        return validate_timezone(value.strip()) if value and value.strip() else None


class BulkImportIn(CamelIn):
    leads: list[LeadIn]
    list_ids: list[str] | None = None


class BulkDeleteIn(CamelIn):
    """Delete a set of leads. Either pass explicit ``ids`` (rows the user
    ticked), or omit them and pass filters to delete everything matching the
    current view (``select all N → delete``). No filters + no ids = nothing."""
    ids: list[str] | None = None
    search: str | None = None
    status: str | None = None
    list_id: str | None = None


class BulkStatusIn(CamelIn):
    ids: list[str]
    status: str


# ------------------------------ Lead lists -------------------------------
class LeadListIn(CamelIn):
    name: str
    description: str | None = None
    color: str | None = None


class LeadListUpdateIn(CamelIn):
    name: str | None = None
    description: str | None = None
    color: str | None = None


# --------------------------------- Steps ---------------------------------
class StepIn(CamelIn):
    id: str | None = None
    type: str
    order: int = 0
    message: str | None = None
    delay_hours: int | None = None
    # Reserved for conditional branches: stored and returned, not executed yet.
    parent_step_id: str | None = None
    branch_condition: dict | None = None


# ------------------------------- Campaigns -------------------------------
class CampaignIn(CamelIn):
    name: str
    description: str | None = None
    account_id: str | None = None
    account_ids: list[str] | None = None
    lead_list_id: str | None = None
    daily_connection_limit: int | None = None
    daily_message_limit: int | None = None
    _connection_limit = _campaign_limit("daily_connection_limit", "send_invite")
    _message_limit = _campaign_limit("daily_message_limit", "send_message")
    timezone: str | None = None
    start_hour: int | None = None
    end_hour: int | None = None
    working_days: list[int] | None = None
    random_delay: bool | None = None
    stop_when_replied: bool | None = None
    stop_when_accepted: bool | None = None
    ai_personalization: bool | None = None
    pause_on_failure: bool | None = None
    audience_source: dict | None = None
    steps: list[StepIn] | None = None


class CampaignUpdateIn(CamelIn):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    account_id: str | None = None
    account_ids: list[str] | None = None
    lead_list_id: str | None = None
    daily_connection_limit: int | None = None
    daily_message_limit: int | None = None
    _connection_limit = _campaign_limit("daily_connection_limit", "send_invite")
    _message_limit = _campaign_limit("daily_message_limit", "send_message")
    timezone: str | None = None
    start_hour: int | None = None
    end_hour: int | None = None
    working_days: list[int] | None = None
    random_delay: bool | None = None
    stop_when_replied: bool | None = None
    stop_when_accepted: bool | None = None
    ai_personalization: bool | None = None
    pause_on_failure: bool | None = None
    audience_source: dict | None = None
    steps: list[StepIn] | None = None


# --------------------------------- Team ----------------------------------
class TeamInviteIn(CamelIn):
    email: str
    role: str | None = "member"  # admin | manager | member


class TeamMemberUpdateIn(CamelIn):
    role: str  # admin | manager | member


class RunActionIn(CamelIn):
    action: str  # retry | skip


# ------------------------------- Templates -------------------------------
class TemplateIn(CamelIn):
    name: str
    category: str | None = "first_message"
    body: str | None = ""


class TemplateUpdateIn(CamelIn):
    name: str | None = None
    category: str | None = None
    body: str | None = None


# ----------------------------- Conversations -----------------------------
class MessageIn(CamelIn):
    conversation_id: str | None = None
    body: str


class ComposeMessageIn(CamelIn):
    """Start a new conversation with a lead from the unibox."""
    lead_id: str
    body: str


class ConversationUpdateIn(CamelIn):
    status: str | None = None
    unread: bool | None = None


# -------------------------------- Settings -------------------------------
class IntegrationIn(CamelIn):
    provider: str
    connected: bool | None = None
    config: dict | None = None


class SettingsUpdateIn(CamelIn):
    """Partial update of any settings facet in one call. Send only the part
    that changed: notification prefs, the two-factor toggle, or a single
    integration to upsert."""
    notification_prefs: dict[str, bool] | None = None
    two_factor_enabled: bool | None = None
    integration: IntegrationIn | None = None


class PasswordChangeIn(CamelIn):
    current_password: str
    new_password: str


# ----------------------------- Prospect import ---------------------------
class LeadImportIn(CamelIn):
    # search_url | sales_navigator_url | post_url | company_url | connections
    source: str
    source_url: str | None = None
    filters: dict | None = None  # for "connections" source: company/title/location/industry/keywords
    list_ids: list[str] | None = None


class ProspectInputIn(CamelIn):
    first_name: str | None = ""
    last_name: str | None = ""
    company: str | None = ""
    job_title: str | None = ""
    linkedin_url: str | None = ""
    location: str | None = None


class ProspectReviewIn(CamelIn):
    """A batch of prospects to validate/dedupe before building a list."""
    urls: list[str] | None = None       # pasted LinkedIn profile URLs
    rows: list[ProspectInputIn] | None = None  # parsed CSV rows


# --------------------------------- AI ------------------------------------
class AIGenerateIn(CamelIn):
    step_type: str | None = "message"  # connection_request | message | follow_up
    tone: str | None = "friendly"
    first_name: str | None = None
    company: str | None = None
    job_title: str | None = None
