from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Hard per-account ceilings. Deliberately constants, not settings: no environment variable, account
# limit, campaign limit or API call can raise them. A limit of 0 means that action is stopped.
DAILY_ACTION_CEILING = 200          # all actions on one account in its day
DAILY_TYPE_CEILINGS = {             # per action type, on one account in its day, across all campaigns
    "send_invite": 40,
    "send_message": 100,
    "visit_profile": 80,
    "follow_profile": 50,
}
WEEKLY_INVITE_CEILING = 150         # connection requests on one account in any seven days


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "sqlite:///./synex.db"

    # Auth
    secret_key: str = ""  # Must be set via .env file
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # CORS
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Password-reset email delivery. When SMTP is not configured, the reset
    # link is logged to the server console instead (dev mode).
    frontend_url: str = "http://localhost:5173"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "no-reply@synex.local"

    # AI drafting. When set, message personalization uses the Anthropic API;
    # otherwise the deterministic local template provider is used.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"

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

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
