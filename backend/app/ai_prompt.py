"""What an AI message is asked to do: per-step settings plus the campaign's shared context become one prompt.

Pure functions: no network, no database. A prompt only ever contains facts the lead record already holds or the campaign owner wrote;
reading more of a profile (recent posts, skills) needs the profile reader, which is not built, so those options are refused.
"""
from __future__ import annotations

import re

TONES = ("auto", "professional", "casual", "witty", "direct")
STRATEGIES = ("auto", "common_ground", "value_offer", "curiosity_hook")
PROFILE_DATA = ("role_company", "recent_posts", "skills", "career", "interests")
AVAILABLE_PROFILE_DATA = ("role_company",)  # the others need a paced profile reader that does not exist yet
INSTRUCTIONS_LIMIT = 2000

TONE_TEXT = {
    "auto": "a natural, friendly tone that fits the prospect's role",
    "professional": "a professional, courteous tone",
    "casual": "a relaxed, casual tone",
    "witty": "a light, witty tone with at most one gentle joke",
    "direct": "a direct tone: short, clear, no filler",
}
STRATEGY_TEXT = {
    "auto": "Choose the approach that suits the details you have.",
    "common_ground": "Lead with something the sender and prospect plausibly share, only if the details show it.",
    "value_offer": "Lead with one concrete way the sender can help, taken from the campaign context.",
    "curiosity_hook": "Open with a short, genuine question that makes the prospect curious.",
}


def check_step_ai(value: dict | None) -> dict | None:
    """The per-message AI settings: {mode: direct|ai, tone, strategy, instructions, profile_data: {...}}."""
    if value is None:
        return None
    mode = value.get("mode", "direct")
    if mode not in ("direct", "ai"):
        raise ValueError("Choose direct or AI assisted.")
    tone, strategy = value.get("tone", "auto"), value.get("strategy", "auto")
    if tone not in TONES:
        raise ValueError("Tone must be one of: " + ", ".join(TONES) + ".")
    if strategy not in STRATEGIES:
        raise ValueError("Strategy must be one of: " + ", ".join(STRATEGIES) + ".")
    instructions = value.get("instructions") or ""
    if not isinstance(instructions, str) or len(instructions) > INSTRUCTIONS_LIMIT:
        raise ValueError(f"Instructions: text of at most {INSTRUCTIONS_LIMIT} characters.")
    data = value.get("profile_data") or {"role_company": True}
    if not isinstance(data, dict) or set(data) - set(PROFILE_DATA) or any(not isinstance(v, bool) for v in data.values()):
        raise ValueError("Profile data options are on or off, from: " + ", ".join(PROFILE_DATA) + ".")
    for key, on in data.items():
        if on and key not in AVAILABLE_PROFILE_DATA:
            raise ValueError("Reading " + key.replace("_", " ") + " needs the profile reader, which is not built yet. Turn it off.")
    return {"mode": mode, "tone": tone, "strategy": strategy, "instructions": instructions.strip(), "profile_data": {k: bool(data.get(k, False)) for k in PROFILE_DATA}}


def wants_ai(step, campaign) -> bool:
    """Does this step get an AI draft? An explicit setting wins; older campaigns follow the campaign's AI switch."""
    config = getattr(step, "ai_config", None)
    if config:
        return config.get("mode") == "ai"
    return bool(getattr(campaign, "ai_personalization", False))


def _clean(text: str, limit: int = 1500) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:limit]


def context_text(context: dict | None) -> str:
    """The campaign's shared knowledge as short labelled lines; empty when the owner wrote nothing."""
    context = context or {}
    labels = (("goals", "Goals, audience, offer and value"), ("proof_points", "Proof points"), ("objections", "Common objections and answers"),
              ("qualification_questions", "Qualification questions"), ("meeting_link", "Meeting link"), ("notes", "Additional notes"))
    lines = [f"{label}: {_clean(context[key])}" for key, label in labels if context.get(key)]
    return "\n".join(lines)


def build_prompt(step_type: str, fields: dict, config: dict | None, context: dict | None, sender: dict | None = None) -> tuple[str, str]:
    """(system prompt, user prompt) for one message."""
    config = config or {}
    tone = TONE_TEXT.get(config.get("tone", "auto"), TONE_TEXT["auto"])
    strategy = STRATEGY_TEXT.get(config.get("strategy", "auto"), STRATEGY_TEXT["auto"])
    rules = ["Reply with the message text only: no preamble, no quotes, no emojis, no placeholder brackets.",
             "Use only the prospect details given; never invent facts about the prospect or the sender.",
             "Never promise anything the campaign context does not state."]
    avoid = [w for w in (context or {}).get("do_not_mention", []) if w]
    if avoid:
        rules.append("Never mention: " + "; ".join(avoid) + ".")
    system = "You write short LinkedIn outreach messages. " + " ".join(rules)
    brief = {"connection_request": "a LinkedIn connection request note of at most 200 characters",
             "follow_up": "a short LinkedIn follow-up to someone who has not replied yet",
             "voice_note": "a short script to be read aloud as a voice note, at most 1000 characters"}.get(step_type, "a short LinkedIn first message to a new connection")
    allowed = config.get("profile_data") or {"role_company": True}
    known = {k: v for k, v in fields.items() if v and (k in ("first_name", "last_name") or allowed.get("role_company", True))}
    parts = [f"Write {brief} in {tone}, one to three sentences. {strategy}",
             "Prospect details: " + (", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in known.items()) or "none known") + "."]
    if sender:
        parts.append("Sender: " + ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in sender.items() if v) + ".")
    shared = context_text(context)
    if shared:
        parts.append("Campaign context:\n" + shared)
    if config.get("instructions"):
        parts.append("Extra instructions from the sender: " + _clean(config["instructions"], INSTRUCTIONS_LIMIT))
    return system, "\n".join(parts)
