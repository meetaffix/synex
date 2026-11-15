"""Message helpers and the pluggable drafting ("AI generate") provider.

LinkedIn actions are executed by the outreach engine (``engine.py`` and
``linkedin_session``), so there is no server-side outreach provider here. What remains is variable
rendering and message drafting.

The default drafting provider personalizes a structured draft from the
prospect's own fields. To use a real LLM, implement ``AIProvider`` and return it
from ``get_ai_provider`` (e.g. gated behind an API-key env var) — no other code
needs to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


def render_variables(text: str | None, lead) -> str:
    """Replace sequence variables with the prospect's real values.

    Supports {{first_name}} {{last_name}} {{name}} {{company}} {{job_title}}
    {{designation}} (alias for job_title) {{location}} {{headline}} {{industry}}.
    """
    if not text:
        return text or ""
    full_name = f"{lead.first_name or ''} {lead.last_name or ''}".strip()
    replacements = {
        "{{first_name}}": lead.first_name or "",
        "{{last_name}}": lead.last_name or "",
        "{{name}}": full_name,
        "{{full_name}}": full_name,
        "{{company}}": lead.company or "",
        "{{job_title}}": lead.job_title or "",
        "{{designation}}": lead.job_title or "",
        "{{location}}": getattr(lead, "location", None) or "",
        "{{headline}}": getattr(lead, "headline", None) or "",
        "{{industry}}": getattr(lead, "industry", None) or "",
    }
    for token, value in replacements.items():
        text = text.replace(token, value)
    return text


# --------------------------------------------------------------------------
# Drafting / "AI generate"
# --------------------------------------------------------------------------
class AIProvider(ABC):
    @abstractmethod
    def generate_message(self, step_type: str, tone: str, ctx: dict) -> str: ...


class TemplateAIProvider(AIProvider):
    """Deterministic local drafting used when no LLM is configured.

    Produces a personalized first draft from the prospect's fields. Unknown
    fields fall back to the sequence variable token so the user can still
    personalize. This is a drafting aid, not a fabricated 'AI result'.
    """

    def generate_message(self, step_type: str, tone: str, ctx: dict) -> str:
        first = ctx.get("first_name") or "{{first_name}}"
        company = ctx.get("company") or "{{company}}"
        role = ctx.get("job_title") or "{{job_title}}"

        if step_type == "connection_request":
            return (
                f"Hi {first}, I came across your work as {role} at {company} "
                f"and would love to connect."
            )
        if step_type == "follow_up":
            return (
                f"Hi {first}, circling back on my last note — happy to share how "
                f"we help teams like {company}. Worth a quick chat?"
            )
        # message / first_message / reply
        return (
            f"Thanks for connecting, {first}! I work with people at companies "
            f"like {company}. Would you be open to a short conversation this week?"
        )


class AnthropicAIProvider(AIProvider):
    """LLM-backed drafting via the Anthropic Messages API (stdlib HTTP only).

    Used automatically when ``ANTHROPIC_API_KEY`` is configured. Any API
    failure raises, and callers fall back to the template provider.
    """

    API_URL = "https://api.anthropic.com/v1/messages"

    STEP_BRIEF = {
        "connection_request": (
            "a LinkedIn connection request note (max 280 characters, no subject line)"
        ),
        "follow_up": "a short LinkedIn follow-up message to someone who hasn't replied yet",
    }

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    def generate_message(self, step_type: str, tone: str, ctx: dict) -> str:
        import json
        import urllib.request

        brief = self.STEP_BRIEF.get(
            step_type, "a short LinkedIn first message to a new connection"
        )
        known = {k: v for k, v in ctx.items() if v}
        prompt = (
            f"Write {brief} in a {tone or 'friendly'} tone.\n"
            f"Prospect details: {json.dumps(known) if known else 'unknown'}.\n"
            "Rules: 1-3 sentences, no emojis, no placeholder brackets, no preamble — "
            "reply with the message text only. Personalize only from the details given; "
            "never invent facts about the prospect."
        )
        body = json.dumps(
            {
                "model": self._model,
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode()
        req = urllib.request.Request(
            self.API_URL,
            data=body,
            headers={
                "content-type": "application/json",
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        text = "".join(
            block.get("text", "") for block in data.get("content", [])
        ).strip()
        if not text:
            raise RuntimeError("empty completion")
        return text


def get_ai_provider() -> AIProvider:
    from .config import settings

    if settings.anthropic_api_key:
        return AnthropicAIProvider(settings.anthropic_api_key, settings.anthropic_model)
    return TemplateAIProvider()
