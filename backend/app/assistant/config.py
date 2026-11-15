"""Assistant configuration. DEEPGRAM_API_KEY is read from the root .env and goes nowhere else: it is never
serialised into a response, a log line or an error message (see ``scrub``)."""
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..config import ENV_FILE


class AssistantConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    deepgram_api_key: str = ""
    deepgram_agent_url: str = "wss://agent.deepgram.com/v1/agent/converse"
    # Standard-tier managed LLM (see docs/ASSISTANT.md for why).
    assistant_llm_provider: str = "anthropic"
    assistant_llm_model: str = "claude-haiku-4-5"
    assistant_voice: str = "aura-2-hera-en"
    assistant_stt_model: str = "nova-3"
    assistant_default_monthly_minutes: int = 60
    assistant_default_idle_seconds: int = 120
    assistant_proposal_ttl_seconds: int = 900
    assistant_ticket_ttl_seconds: int = 30
    assistant_max_sessions_per_workspace: int = 5


assistant_config = AssistantConfig()

LANGUAGES = ("en", "en-IN")


def scrub(text: str) -> str:
    """Remove the API key from any string that might be logged or returned."""
    key = assistant_config.deepgram_api_key
    return text.replace(key, "[redacted]") if key and key in text else text
