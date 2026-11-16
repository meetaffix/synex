import re
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Hard per-account ceilings. Deliberately constants, not settings: no environment variable, account
# limit, campaign limit or API call can raise them. A limit of 0 means that action is stopped.
DAILY_ACTION_CEILING = 200          # all actions on one account in its day
DAILY_TYPE_CEILINGS = {             # per action type, on one account in its day, across all campaigns
    "send_invite": 40,
    "send_message": 100,
    "visit_profile": 80,
    "follow_profile": 50,
    "check_connection": 80,         # opens a profile page, so it is counted like a visit
    "sync_inbox": 48,               # one inbox read every 30 minutes at most
    "withdraw_invite": 20,           # taking back a stale connection request: opens a profile page, so it is counted like a visit
    "sync_connections": 12,         # one read of the sender's own connection list or received invitations, a few pages each
    "collect_leads": 20,            # one page of search results, post reactions or a list: each opens LinkedIn pages
}
WEEKLY_INVITE_CEILING = 150         # connection requests on one account in any seven days


# A managed CockroachDB plan allows about 5 active connections. The API and both workers together never open more than
# DB_CONNECTION_BUDGET, which leaves one for migrations and admin. check_env and a test fail if the pools below exceed it.
DB_CONNECTION_BUDGET = 4
# Concurrent Chromium instances are the main cost of a hosted worker (about 0.5 GB each). LINKEDIN_SESSION_MAX_BROWSERS
# sets the cap; no setting can raise it above this ceiling, and check_env fails above it.
MAX_BROWSERS_CEILING = 5
DB_POOLS = {"api": 2, "outreach_worker": 1, "publishing_worker": 1}  # one pool per process; no overflow connections

# Campaign preparation: AI drafts are generated before launch, never while sending (docs/ASSISTANT.md, "Drafts").
DRAFT_CAP_PER_CAMPAIGN = 200        # most drafts one campaign may generate (a cap on cost and on review work)
DRAFT_BATCH_SIZE = 5                # drafts generated per batch; each batch is its own short database transaction
DRAFT_SECONDS_ESTIMATE = 10         # assumed Voice Agent connection time per draft, for the cost estimate
DEEPGRAM_USD_PER_MINUTE = 0.075     # Voice Agent Standard tier, pay as you go (docs/ASSISTANT.md)

# The one .env for the whole project lives at the project root, next to backend/ and frontend/.
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    # Database
    database_url: str = "sqlite:///./synex.db"

    # Auth
    secret_key: str = ""  # Must be set via .env file
    algorithm: str = "HS256"

    # CORS
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Optional regular expression for origins that cannot be listed one by one, such as the preview deployments of
    # one Vercel project. It must match the WHOLE origin and be specific to this project (never a "*.vercel.app"
    # wildcard, which would admit every Vercel site). The same set is used for CORS, the origin check on writes and
    # Clerk's authorized parties. Empty by default.
    cors_origin_regex: str = ""

    # Password-reset email delivery. When SMTP is not configured, the reset
    # link is logged to the server console instead (dev mode).
    frontend_url: str = "http://localhost:5173"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "no-reply@synex.local"

    # Cloud execution mode: encrypts stored li_at / JSESSIONID cookies at rest.
    # Falls back to a key derived from secret_key when unset (fine for dev;
    # set a dedicated key in production so cookie secrets are independently
    # rotatable from the JWT secret).
    encryption_key: str = ""
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    linkedin_redirect_uri: str = "http://localhost:8010/linkedin/callback"
    linkedin_scopes: str = "openid profile email w_member_social"
    linkedin_api_version: str = "202610"
    cookie_secure: bool = False

    # Server-side browser sessions for LinkedIn accounts (see app/linkedin_session).
    linkedin_session_max_browsers: int = 3
    linkedin_session_attempt_timeout_seconds: int = 600
    linkedin_session_poll_interval_seconds: float = 1.0
    linkedin_session_headless: bool = True
    # On a hosted server: refuse to open a browser for any account that has no proxy (a datacenter address is the risk).
    require_account_proxy: bool = False
    # Where a failed login's redacted screenshot goes (this machine only, never committed). Empty: backend/captures.
    linkedin_capture_dir: str = ""
    # Proxy test: one request to this neutral endpoint (never LinkedIn), through the proxy under test.
    linkedin_proxy_test_url: str = "https://ipinfo.io/json"
    linkedin_proxy_test_timeout_seconds: float = 10
    # Proxies on private or loopback addresses are refused unless this is enabled.
    linkedin_proxy_test_allow_private: bool = False

    # Outreach executor (python -m app.outreach_worker).
    outreach_kill_switch: bool = False  # stops all task execution; also settable at runtime by a platform admin
    outreach_tick_interval_seconds: float = 30
    outreach_action_gap_min_seconds: float = 45  # pause between actions on one account, on top of the engine's own pacing
    outreach_action_gap_max_seconds: float = 180
    outreach_batch_max_actions: int = 5  # actions per browser session before it is closed
    outreach_weekly_connection_limit: int = 100  # never above WEEKLY_INVITE_CEILING; the engine takes the lower
    outreach_max_consecutive_failures: int = 5
    outreach_task_max_attempts: int = 3  # automatic tries for tasks that failed before touching the page
    outreach_task_retry_backoff_seconds: float = 120
    outreach_lease_seconds: float = 300  # an account's browser lease; renewed before every action
    outreach_stale_task_seconds: float = 600  # a task running longer than this was abandoned: needs_review
    outreach_acceptance_check_interval_hours: float = 12
    outreach_inbox_sync_interval_minutes: float = 15

    # Which service writes AI drafts: "auto" (Deepgram when its key is set, else the built-in templates), "deepgram", "ollama" (a model on
    # this computer or network, free and private) or "template". Paid services stay optional.
    ai_provider: str = "auto"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2"

    # Integrations. Webhooks to private or local addresses are refused unless this is on (for testing on one machine).
    allow_private_webhooks: bool = False
    # Notification email. With no SMTP host, emails are only written to the outbox table, which the app can show.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    # Authentication. "local" is the built-in email and password sign-in (used by the tests); "clerk" accepts only
    # Clerk session tokens (see docs/CLERK_MIGRATION.md). One variable switches back if Clerk is misconfigured.
    auth_provider: str = "local"
    clerk_secret_key: str = ""
    clerk_publishable_key: str = Field("", validation_alias=AliasChoices("CLERK_PUBLISHABLE_KEY", "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "VITE_CLERK_PUBLISHABLE_KEY"))
    clerk_issuer: str = ""  # optional override of the issuer derived from the publishable key
    clerk_webhook_secret: str = Field("", validation_alias=AliasChoices("CLERK_WEBHOOK_SECRET", "CLERK_WEBHOOK_SIGNING_SECRET"))
    clerk_api_url: str = "https://api.clerk.com"

    @property
    def effective_max_browsers(self) -> int:
        """The browser cap in force: the setting, never below 1 and never above MAX_BROWSERS_CEILING."""
        return max(1, min(int(self.linkedin_session_max_browsers), MAX_BROWSERS_CEILING))

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def origin_allowed(self, origin: str | None) -> bool:
        """True when ``origin`` is listed in CORS_ORIGINS or fully matches CORS_ORIGIN_REGEX."""
        if not origin:
            return False
        if origin in self.cors_origin_list:
            return True
        return bool(self.cors_origin_regex) and re.fullmatch(self.cors_origin_regex, origin) is not None


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
