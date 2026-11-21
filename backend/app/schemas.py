"""Request body schemas (camelCase in, validated)."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from . import campaign_settings
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
    full_name: str | None = Field(None, max_length=200)
    email: EmailStr | None = None
    company: str | None = Field(None, max_length=160)
    phone: str | None = Field(None, max_length=40)
    designation: str | None = Field(None, max_length=120)
    role: str | None = None  # accepted and ignored: nobody changes their own role here
    avatar_url: str | None = Field(None, max_length=2048)

    @field_validator("full_name")
    @classmethod
    def _name(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not 1 <= len(v) <= 120:
            raise ValueError("Enter your name, up to 120 characters.")
        return v

    @field_validator("phone")
    @classmethod
    def _phone(cls, v):
        if v and v.strip() and not re.fullmatch(r"[0-9+()\-.\s]{3,40}", v.strip()):
            raise ValueError("Enter a phone number using digits, spaces, + ( ) - or .")
        return v

    @field_validator("avatar_url")
    @classmethod
    def _picture(cls, v):
        if v and not v.strip().lower().startswith("https://"):
            raise ValueError("A picture must be a web address starting with https://.")
        return v


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
    first_name: str | None = Field("", max_length=200)
    last_name: str | None = Field("", max_length=200)
    company: str | None = Field("", max_length=200)
    job_title: str | None = Field("", max_length=200)
    headline: str | None = Field(None, max_length=400)
    linkedin_url: str | None = Field("", max_length=500)
    email: str | None = Field(None, max_length=254)
    phone: str | None = Field(None, max_length=40)
    location: str | None = Field(None, max_length=200)
    industry: str | None = Field(None, max_length=200)
    timezone: str | None = None  # IANA name; overrides the campaign timezone for working hours
    tags: list[str] | None = Field(None, max_length=50)
    status: str | None = "new"
    notes: str | None = Field(None, max_length=5000)
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
    first_name: str | None = Field(None, max_length=200)
    last_name: str | None = Field(None, max_length=200)
    company: str | None = Field(None, max_length=200)
    job_title: str | None = Field(None, max_length=200)
    headline: str | None = Field(None, max_length=400)
    linkedin_url: str | None = Field(None, max_length=500)
    email: str | None = Field(None, max_length=254)
    phone: str | None = Field(None, max_length=40)
    location: str | None = Field(None, max_length=200)
    industry: str | None = Field(None, max_length=200)
    timezone: str | None = Field(None, max_length=64)
    tags: list[str] | None = Field(None, max_length=50)
    status: str | None = Field(None, max_length=40)
    notes: str | None = Field(None, max_length=5000)
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
    name: str = Field(max_length=200)
    description: str | None = Field(None, max_length=1000)
    color: str | None = Field(None, max_length=40)


class LeadListUpdateIn(CamelIn):
    name: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=1000)
    color: str | None = Field(None, max_length=40)


# --------------------------------- Steps ---------------------------------
class StepIn(CamelIn):
    id: str | None = None
    type: str
    order: int = Field(0, ge=0, le=1000)
    message: str | None = Field(None, max_length=3000)
    delay_hours: int | None = Field(None, ge=0, le=24 * 90)  # at most 90 days
    # Reserved for conditional branches: stored and returned, not executed yet.
    parent_step_id: str | None = None
    branch_condition: dict | None = None
    ai_config: dict | None = None
    config: dict | None = None

    @field_validator("type")
    @classmethod
    def _type(cls, value):
        from .step_types import known
        if not known(value):
            raise ValueError("That is not a step Synex knows.")
        return value

    @model_validator(mode="after")
    def _config(self):
        from .step_types import check_config
        self.config = check_config(self.type, self.config)
        return self

    @field_validator("ai_config")
    @classmethod
    def _ai_config(cls, value):
        from .ai_prompt import check_step_ai
        return check_step_ai(value)


# ------------------------------- Campaigns -------------------------------
class CampaignSettingsIn(CamelIn):
    """Schedule, exclusions, sender allocation, AI context and sequence mode; validated by campaign_settings."""
    week_schedule: dict | None = None
    exclusions: dict | None = None
    allocation: dict | None = None
    ai_context: dict | None = None
    webhook: dict | None = None
    sequence_mode: str | None = None
    graph: dict | None = None

    @field_validator("week_schedule")
    @classmethod
    def _week(cls, value):
        return campaign_settings.check_week_schedule(value)

    @field_validator("exclusions")
    @classmethod
    def _exclusions(cls, value):
        return campaign_settings.check_exclusions(value)

    @field_validator("webhook")
    @classmethod
    def _webhook(cls, value):
        return campaign_settings.check_webhook(value)

    @field_validator("allocation")
    @classmethod
    def _allocation(cls, value):
        return campaign_settings.check_allocation(value)

    @field_validator("ai_context")
    @classmethod
    def _context(cls, value):
        return campaign_settings.check_ai_context(value)

    @field_validator("sequence_mode")
    @classmethod
    def _mode(cls, value):
        if value not in (None, "classic", "smart"):
            raise ValueError("Choose classic or smart.")
        return value


class CampaignIn(CampaignSettingsIn):
    name: str = Field(max_length=200)
    description: str | None = Field(None, max_length=2000)
    account_id: str | None = None
    account_ids: list[str] | None = None
    lead_list_id: str | None = None
    daily_connection_limit: int | None = None
    daily_message_limit: int | None = None
    _connection_limit = _campaign_limit("daily_connection_limit", "send_invite")
    _message_limit = _campaign_limit("daily_message_limit", "send_message")
    timezone: str | None = None
    start_hour: int | None = Field(None, ge=0, le=23)
    end_hour: int | None = Field(None, ge=1, le=24)

    @model_validator(mode="after")
    def _hours_in_order(self):
        if self.start_hour is not None and self.end_hour is not None and self.start_hour >= self.end_hour:
            raise ValueError("The start hour must be before the end hour.")
        return self
    working_days: list[int] | None = None
    random_delay: bool | None = None
    stop_when_replied: bool | None = None
    stop_when_accepted: bool | None = None
    ai_personalization: bool | None = None
    pause_on_failure: bool | None = None
    audience_source: dict | None = None
    steps: list[StepIn] | None = None


class CampaignUpdateIn(CampaignSettingsIn):
    confirm_send: bool = False  # set by the screen after the person has seen who is sent to next; needed to resume a paused campaign
    name: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=2000)
    status: str | None = None
    account_id: str | None = None
    account_ids: list[str] | None = None
    lead_list_id: str | None = None
    daily_connection_limit: int | None = None
    daily_message_limit: int | None = None
    _connection_limit = _campaign_limit("daily_connection_limit", "send_invite")
    _message_limit = _campaign_limit("daily_message_limit", "send_message")
    timezone: str | None = None
    start_hour: int | None = Field(None, ge=0, le=23)
    end_hour: int | None = Field(None, ge=1, le=24)

    @model_validator(mode="after")
    def _hours_in_order(self):
        if self.start_hour is not None and self.end_hour is not None and self.start_hour >= self.end_hour:
            raise ValueError("The start hour must be before the end hour.")
        return self
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
    confirm_send: bool = False  # retry and skip can start a real send, so the person must have seen it first


# ------------------------------- Templates -------------------------------
def check_shortcut(value: str | None) -> str | None:
    """A saved-reply shortcut: 2 to 20 lowercase letters, digits or dashes; no slash (the slash is typed in the reply box)."""
    import re
    if value is None or not value.strip():
        return None
    text = value.strip().lstrip("/").lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,19}", text):
        raise ValueError("A shortcut is 2 to 20 lowercase letters, digits or dashes, such as thanks.")
    return text


class TemplateIn(CamelIn):
    name: str = Field(max_length=200)
    category: str | None = "first_message"
    body: str | None = Field("", max_length=5000)
    shortcut: str | None = Field(None, max_length=40)

    @field_validator("shortcut")
    @classmethod
    def _shortcut(cls, value):
        return check_shortcut(value)


class TemplateUpdateIn(CamelIn):
    name: str | None = Field(None, max_length=200)
    category: str | None = None
    body: str | None = Field(None, max_length=5000)
    shortcut: str | None = Field(None, max_length=40)

    @field_validator("shortcut")
    @classmethod
    def _shortcut(cls, value):
        return check_shortcut(value)


# ----------------------------- Conversations -----------------------------
class MessageIn(CamelIn):
    conversation_id: str | None = None
    body: str = Field(max_length=8000)


class ComposeMessageIn(CamelIn):
    """Start a new conversation with a lead from the unibox."""
    lead_id: str
    body: str = Field(max_length=8000)


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
    first_name: str | None = Field("", max_length=200)
    last_name: str | None = Field("", max_length=200)
    company: str | None = Field("", max_length=200)
    job_title: str | None = Field("", max_length=200)
    linkedin_url: str | None = Field("", max_length=500)
    location: str | None = Field(None, max_length=200)


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
