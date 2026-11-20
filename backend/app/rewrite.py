"""Humanized rewrite of a message the user wrote: same meaning and facts, plainer and warmer, never invented.

A user action while writing a sequence, never part of sending. The configured provider (Deepgram, Ollama) does the rewrite;
with no AI service the local cleanup below still removes the stiffest phrasing. {{variables}} and {spin|tax} survive either way.
"""
from __future__ import annotations

import re

VARIABLE = re.compile(r"\{\{\s*[A-Za-z_][A-Za-z0-9_]*\s*\}\}")
SPINTAX = re.compile(r"\{[^{}|]+(?:\|[^{}]+)+\}")

SYSTEM = ("You rewrite LinkedIn messages so they sound like a real person typed them. Keep the meaning, the facts and the length about the same. "
          "Use plain, short, warm sentences. No corporate or salesy phrases, no emojis, no hashtags, no em dashes, no exclamation marks unless the original has one. "
          "Keep every {{variable}} and every {a|b} option exactly as written. Reply with the message text only: no quotes, no preamble.")

STIFF = [
    (r"\bI hope this (message|email|note) finds you well[.,!]?\s*", ""),
    (r"\bI hope you(?:'| a)re doing well[.,!]?\s*", ""),
    (r"\bI wanted to reach out (?:to you )?(?:because|and)\b", "I'm reaching out because"),
    (r"\bI would like to\b", "I'd like to"),
    (r"\bI would love to\b", "I'd love to"),
    (r"\bdo not hesitate to\b", "feel free to"),
    (r"\bat your earliest convenience\b", "when you can"),
    (r"\bleverage\b", "use"),
    (r"\butili[sz]e\b", "use"),
    (r"\bsynerg(?:y|ies)\b", "overlap"),
    (r"\bin order to\b", "to"),
    (r"\bkindly\b", "please"),
]


def tidy(text: str) -> str:
    """Rule-based cleanup used with no AI service, and as the safe fallback."""
    out = text.replace("—", ",").replace("–", "-")
    for pattern, replacement in STIFF:
        out = re.sub(pattern, replacement, out, flags=re.I)
    out = re.sub(r"[ \t]+", " ", out)
    out = re.sub(r"\s+([,.!?])", r"\1", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    out = out.strip()
    return out[:1].upper() + out[1:] if out and out[0].islower() else out


def _keeps_tokens(original: str, new: str) -> bool:
    norm = lambda t: sorted(re.sub(r"\s+", "", m) for m in VARIABLE.findall(t))
    return norm(original) == norm(new) and all(s in new for s in SPINTAX.findall(original))


def _ask(provider: str, text: str) -> str:
    prompt = f"Rewrite this message:\n\n{text}"
    if provider == "deepgram":
        from .deepgram_text import complete
        return complete(SYSTEM, prompt)
    if provider == "ollama":
        import json
        import urllib.request

        from .config import settings
        body = json.dumps({"model": settings.ollama_model, "system": SYSTEM, "prompt": prompt, "stream": False, "options": {"temperature": 0.6}}).encode()
        request = urllib.request.Request(settings.ollama_url.rstrip("/") + "/api/generate", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=90) as response:  # noqa: S310 - the address is the owner's own setting
            return (json.loads(response.read().decode()).get("response") or "").strip()
    raise RuntimeError("no AI service")


def humanize(text: str, max_length: int | None = None, provider: str | None = None) -> dict:
    """{text, provider, changed}. ``provider`` is the one that wrote it: deepgram, ollama or local (rule-based cleanup)."""
    from .providers import provider_name
    original = text.strip()
    name = provider or provider_name()
    if name in ("deepgram", "ollama"):
        try:
            rewritten = _ask(name, original).strip().strip('"')
            if rewritten and _keeps_tokens(original, rewritten) and (max_length is None or len(rewritten) <= max_length):
                return {"text": rewritten, "provider": name, "changed": rewritten != original}
        except Exception:  # noqa: BLE001 - any failure falls back to the local cleanup
            pass
    cleaned = tidy(original)
    if max_length is not None:
        cleaned = cleaned[:max_length]
    return {"text": cleaned, "provider": "local", "changed": cleaned != original}
