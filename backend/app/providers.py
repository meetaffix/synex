"""Message helpers and the pluggable drafting ("AI generate") provider.

LinkedIn actions are executed by the outreach engine (``engine.py`` and
``linkedin_session``), so there is no server-side outreach provider here. What remains is variable
rendering and message drafting.

The default drafting provider personalizes a structured draft from the
prospect's own fields. With ``DEEPGRAM_API_KEY`` set, ``get_ai_provider`` returns the
Deepgram-backed provider instead; Deepgram is the only AI service Synex uses.
"""

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod

# {option one|option two|option three}: one option is chosen per message. A single "{...}" without a pipe, and the
# {{variable}} tokens, are left alone.
_SPINTAX = re.compile(r"(?<!\{)\{([^{}|]*(?:\|[^{}|]*)+)\}(?!\})")


def spin(text: str, seed: str = "") -> str:
    """Pick one option from every {a|b|c} group. The choice depends only on ``seed`` and the position of the group, so
    the same lead always gets the same wording, and the dry run shows exactly what the engine will send."""
    counter = iter(range(10_000))

    def choose(match: re.Match) -> str:
        options = match.group(1).split("|")
        digest = hashlib.sha256(f"{seed}:{next(counter)}".encode()).digest()
        return options[int.from_bytes(digest[:4], "big") % len(options)]

    return _SPINTAX.sub(choose, text)


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
        # The same facts under the names LinkedIn-sourced leads use in other tools.
        "{{linkedin_firstName}}": lead.first_name or "",
        "{{linkedin_lastName}}": lead.last_name or "",
        "{{linkedin_company}}": lead.company or "",
        "{{linkedin_jobTitle}}": lead.job_title or "",
        "{{linkedin_headline}}": getattr(lead, "headline", None) or "",
        "{{linkedin_location}}": getattr(lead, "location", None) or "",
    }
    for token, value in replacements.items():
        text = text.replace(token, value)
    for name, value in (getattr(lead, "variables", None) or {}).items():  # per-lead custom variables, e.g. {{eventName}}
        text = text.replace("{{" + str(name) + "}}", str(value))
    return spin(text, str(getattr(lead, "id", "") or full_name))


def sender_values(account) -> dict:
    """The sending account's own details: first and last name, company and title, as far as its LinkedIn profile gave them."""
    name = (getattr(account, "name", "") or "").strip()
    first, _, last = name.partition(" ")
    headline = (getattr(account, "headline", "") or "").strip()
    company = headline.split(" at ", 1)[1].strip() if " at " in headline else ""
    title = headline.split(" at ", 1)[0].strip() if headline else ""
    return {"sender_firstName": first, "sender_lastName": last, "sender_company": company, "sender_title": title}


def render_sender_variables(text: str | None, account) -> str:
    """Fill {{sender_*}} once the sending account is known (the engine knows it only when it picks one)."""
    out = text or ""
    if account is None:
        return out
    for key, value in sender_values(account).items():
        out = out.replace("{{" + key + "}}", value)
    return out


_TOKEN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def unresolved_variables(text: str | None) -> list[str]:
    """Variables still in the text after filling: the lead has no value for them, so they would be sent as written."""
    return sorted({m.group(1) for m in _TOKEN.finditer(text or "")})


# --------------------------------------------------------------------------
# Drafting / "AI generate"
# --------------------------------------------------------------------------
class AIProvider(ABC):
    @abstractmethod
    def generate_message(self, step_type: str, tone: str, ctx: dict, brief: dict | None = None) -> str:
        """``brief`` (optional) carries {"config": per-step AI settings, "context": the campaign's shared context}."""


class TemplateAIProvider(AIProvider):
    """Deterministic local drafting used when no LLM is configured.

    Produces a personalized first draft from the prospect's fields. Unknown
    fields fall back to the sequence variable token so the user can still
    personalize. This is a drafting aid, not a fabricated 'AI result'.
    """

    def generate_message(self, step_type: str, tone: str, ctx: dict, brief: dict | None = None) -> str:
        first = ctx.get("first_name") or "{{first_name}}"
        company = ctx.get("company") or "{{company}}"
        role = ctx.get("job_title") or "{{job_title}}"

        seed = f"{step_type}:{first}:{company}"
        if step_type == "connection_request":
            text = (
                f"{{Hi|Hello}} {first}, {{I came across|I noticed|I saw}} your work as {role} at {company} "
                f"and {{would love to connect|would be glad to connect}}."
            )
        elif step_type == "follow_up":
            text = (
                f"{{Hi|Hello}} {first}, {{circling back on|following up on}} my last note. {{Happy to share|Glad to share}} how "
                f"we help teams like {company}. {{Worth a quick chat?|Open to a quick chat?}}"
            )
        else:  # message / first_message / reply
            text = (
                f"{{Thanks for connecting|Great to be connected}}, {first}! I work with people at companies "
                f"like {company}. {{Would you be open to|Could we set up}} a short conversation this week?"
            )
        return spin(text, seed)


class DeepgramAIProvider(AIProvider):
    """LLM-backed drafting through Deepgram's Voice Agent, the only AI service Synex uses (see ``deepgram_text``).

    Used automatically when ``DEEPGRAM_API_KEY`` is configured. Any failure raises, and callers fall back to the
    template provider.
    """

    STEP_BRIEF = {
        "connection_request": "a LinkedIn connection request note (max 280 characters, no subject line)",
        "follow_up": "a short LinkedIn follow-up message to someone who hasn't replied yet",
    }
    SYSTEM = ("You write short LinkedIn outreach messages. Reply with the message text only: no preamble, no quotes, "
              "no emojis, no placeholder brackets. Personalize only from the details given and never invent facts "
              "about the prospect.")

    def generate_message(self, step_type: str, tone: str, ctx: dict, brief: dict | None = None) -> str:
        import json

        from .deepgram_text import complete

        if brief is not None:
            from .ai_prompt import build_prompt
            system, prompt = build_prompt(step_type, ctx, brief.get("config"), brief.get("context"), brief.get("sender"))
            return complete(system, prompt)
        step_brief = self.STEP_BRIEF.get(step_type, "a short LinkedIn first message to a new connection")
        known = {k: v for k, v in ctx.items() if v}
        prompt = (f"Write {step_brief} in a {tone or 'friendly'} tone, 1-3 sentences.\n"
                  f"Prospect details: {json.dumps(known) if known else 'unknown'}.")
        return complete(self.SYSTEM, prompt)


class OllamaAIProvider(AIProvider):
    """A model running on this computer or network through Ollama (MIT licence; the models carry their own licences). Free and private.

    Talks to ``OLLAMA_URL`` over plain HTTP with the standard library; nothing is sent anywhere else. Any failure raises, and callers fall
    back to the template provider.
    """

    def generate_message(self, step_type: str, tone: str, ctx: dict, brief: dict | None = None) -> str:
        import json
        import urllib.request

        from .ai_prompt import build_prompt
        from .config import settings

        brief = brief or {}
        system, prompt = build_prompt(step_type, ctx, brief.get("config"), brief.get("context"), brief.get("sender"))
        body = json.dumps({"model": settings.ollama_model, "system": system, "prompt": prompt, "stream": False, "options": {"temperature": 0.7}}).encode()
        request = urllib.request.Request(settings.ollama_url.rstrip("/") + "/api/generate", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=90) as response:  # noqa: S310 - the address is the owner's own setting
            text = (json.loads(response.read().decode()).get("response") or "").strip()
        if not text:
            raise RuntimeError("Ollama returned an empty reply.")
        return text


def provider_name() -> str:
    """Which service writes drafts right now: deepgram, ollama or template."""
    from .assistant.config import assistant_config
    from .config import settings

    choice = (settings.ai_provider or "auto").lower()
    if choice == "ollama":
        return "ollama"
    if choice == "template":
        return "template"
    if choice in ("auto", "deepgram") and assistant_config.deepgram_api_key:
        return "deepgram"
    return "template"


def get_ai_provider() -> AIProvider:
    name = provider_name()
    if name == "ollama":
        return OllamaAIProvider()
    if name == "deepgram":
        return DeepgramAIProvider()
    return TemplateAIProvider()
