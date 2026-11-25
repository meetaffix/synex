"""Request and response models. JSON keys are camelCase."""
from datetime import datetime, timezone
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from .. import models
from ..sessions import aware
from .identity import normalize_identifier, validate_proxy_url, validate_timezone
from .store import can_change_sync_mode
from ..config import DAILY_ACTION_CEILING, DAILY_TYPE_CEILINGS, WEEKLY_INVITE_CEILING
from ..engine import _local, account_tz, configured_daily_limit
from .manager import Attempt

AccountStatus = Literal["connected", "needs_reconnect", "restricted", "paused", "disconnected"]
SyncMode = Literal["all", "synex_only"]
ProxyErrorCode = Literal["proxy_not_allowed", "proxy_unreachable", "proxy_rejected", "timeout", "bad_response", "unknown"]


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


def _proxy(value: str | None) -> str | None:
    return validate_proxy_url(value) if value else value


class LoginIn(CamelModel):
    """Sign-in details. `email` is accepted as a deprecated alias of `identifier` for one release."""

    identifier: str = Field(validation_alias=AliasChoices("identifier", "email"), max_length=320)
    password: str = Field(min_length=1, max_length=256, repr=False)

    @field_validator("identifier")
    @classmethod
    def _identifier(cls, value: str) -> str:
        return normalize_identifier(value)


class ConnectIn(LoginIn):
    proxy_url: str | None = None
    timezone: str | None = None
    sync_mode: SyncMode | None = None  # omitted: synex_only for a new account, unchanged otherwise

    _proxy = field_validator("proxy_url")(_proxy)

    @field_validator("timezone")
    @classmethod
    def _timezone(cls, value: str | None) -> str | None:
        return validate_timezone(value) if value else None


class ReconnectIn(LoginIn):
    sync_mode: SyncMode | None = None


class CodeIn(CamelModel):
    code: str = Field(min_length=4, max_length=10, pattern=r"^\d+$", repr=False)


class AccountPatch(CamelModel):
    daily_action_limit: int | None = Field(default=None, ge=0, le=DAILY_ACTION_CEILING)  # 0 stops the account
    paused: bool | None = None
    proxy_url: str | None = None  # null clears the proxy; omit to leave it unchanged
    sync_mode: SyncMode | None = None

    _proxy = field_validator("proxy_url")(_proxy)


class ProxyTestIn(CamelModel):
    proxy_url: str

    @field_validator("proxy_url")
    @classmethod
    def _required_proxy(cls, value: str) -> str:
        return validate_proxy_url(value)


class ProxyErrorOut(CamelModel):
    code: ProxyErrorCode
    message: str


class ProxyTestOut(CamelModel):
    ok: bool
    latency_ms: int | None = None
    exit_ip: str | None = None
    country: str | None = None
    error: ProxyErrorOut | None = None


class ChallengeOut(CamelModel):
    type: Literal["email_code", "sms_code", "authenticator_code"]
    hint: str | None = None


class ErrorOut(CamelModel):
    code: Literal["invalid_credentials", "timeout", "proxy_error", "proxy_required", "cancelled", "unknown"]
    message: str


class AttemptOut(CamelModel):
    attempt_id: str
    state: Literal["starting", "awaiting_code", "awaiting_app_approval", "awaiting_manual_verification", "succeeded", "failed"]
    challenge: ChallengeOut | None = None
    error: ErrorOut | None = None
    account_id: str | None = None

    @classmethod
    def from_attempt(cls, attempt: Attempt) -> "AttemptOut":
        challenge, error = attempt.challenge, attempt.error
        return cls(attempt_id=attempt.id, state=attempt.state, account_id=attempt.account_id,
                   challenge=ChallengeOut(type=challenge.type, hint=challenge.hint) if challenge else None,
                   error=ErrorOut(code=error[0], message=error[1]) if error else None)


class CeilingsOut(CamelModel):
    """The hard per-account ceilings, so the UI can show them beside each limit."""
    daily_actions: int
    connection_requests_per_day: int
    connection_requests_per_week: int
    messages_per_day: int
    profile_visits_per_day: int
    follows_per_day: int

    @classmethod
    def current(cls) -> "CeilingsOut":
        return cls(daily_actions=DAILY_ACTION_CEILING, connection_requests_per_day=DAILY_TYPE_CEILINGS["send_invite"],
                   connection_requests_per_week=WEEKLY_INVITE_CEILING, messages_per_day=DAILY_TYPE_CEILINGS["send_message"],
                   profile_visits_per_day=DAILY_TYPE_CEILINGS["visit_profile"], follows_per_day=DAILY_TYPE_CEILINGS["follow_profile"])


def _today_limit(account: models.LinkedInAccount, now: datetime | None) -> int:
    from ..engine import effective_daily_limit  # imported here: the engine imports this package
    return effective_daily_limit(account, now or datetime.now(timezone.utc))


class AccountOut(CamelModel):
    id: str
    name: str
    headline: str | None
    location: str | None = None
    company: str | None = None
    profile_url: str | None
    avatar_url: str | None
    status: AccountStatus
    daily_action_limit: int
    # What the account may really do today: the configured limit after warm-up. Shown as "18 of 50 today".
    daily_action_limit_today: int = 0
    daily_actions_used: int
    ceilings: CeilingsOut
    proxy_configured: bool
    sync_mode: SyncMode
    can_change_sync_mode: bool  # for the person making this request
    paused_reason: str | None
    last_checked_at: datetime | None
    connected_at: datetime | None

    @classmethod
    def from_model(cls, account: models.LinkedInAccount, viewer_id: str, now: datetime | None = None) -> "AccountOut":
        # The engine rolls the daily counters over at midnight in the account's own timezone; so does this.
        today = _local(now or datetime.now(timezone.utc), account_tz(account)).date().isoformat()
        return cls(
            id=account.id, name=account.name, headline=account.headline, location=account.location, company=account.company,
            profile_url=account.linkedin_url,
            avatar_url=account.avatar_url,
            status="paused" if account.status in ("paused", "deactivated", "archived") else (account.session_status or "disconnected"),
            daily_action_limit=configured_daily_limit(account),
            daily_action_limit_today=_today_limit(account, now),
            daily_actions_used=(account.daily_actions_used or 0) if account.last_action_date == today else 0,
            ceilings=CeilingsOut.current(),
            proxy_configured=bool(account.proxy_url_encrypted),
            sync_mode=account.sync_mode or "synex_only",
            can_change_sync_mode=can_change_sync_mode(account, viewer_id),
            paused_reason=account.paused_reason,
            last_checked_at=aware(account.last_checked_at), connected_at=aware(account.connected_at))


class ReconnectLinkOut(CamelModel):
    url: str
    expires_at: datetime


class ReconnectInfoOut(CamelModel):
    account_name: str
    avatar_url: str | None
    expires_at: datetime
