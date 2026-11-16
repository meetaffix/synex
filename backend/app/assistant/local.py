"""The text assistant on a model running on this computer or network (Ollama). No paid service, nothing leaves the network.

It uses the same tool registry as the voice assistant, so the same permission checks, audit log and confirmation cards apply: a write tool only
creates a proposal that the signed-in person confirms with a click. The model is asked for tool calls through Ollama's chat API.
"""
from __future__ import annotations

import json
import urllib.request

from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..deps import resolve_workspace
from . import tools  # noqa: F401  (registers the tools)
from .prompt import build_prompt, clean_page
from .registry import function_definitions, run_tool

MAX_ROUNDS = 4
MAX_HISTORY = 12


class LocalAssistantError(Exception):
    pass


def _chat(messages: list[dict], tools: list[dict]) -> dict:
    body = json.dumps({"model": settings.ollama_model, "messages": messages, "tools": tools, "stream": False, "options": {"temperature": 0.3}}).encode()
    request = urllib.request.Request(settings.ollama_url.rstrip("/") + "/api/chat", data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 - the address is the owner's own setting
            return json.loads(response.read().decode()).get("message") or {}
    except OSError:
        raise LocalAssistantError("The local model is not reachable. Start Ollama, or check OLLAMA_URL and OLLAMA_MODEL.") from None


def available() -> dict:
    """Whether the local model answers, for the settings screen."""
    try:
        with urllib.request.urlopen(settings.ollama_url.rstrip("/") + "/api/tags", timeout=3) as response:  # noqa: S310
            names = [m.get("name") for m in json.loads(response.read().decode()).get("models", [])]
        return {"reachable": True, "model": settings.ollama_model, "installed": any((n or "").split(":")[0] == settings.ollama_model.split(":")[0] for n in names)}
    except Exception:  # noqa: BLE001 - not running is a normal state
        return {"reachable": False, "model": settings.ollama_model, "installed": False}


def chat(db: Session, actor: models.User, text: str, history: list[dict], page: dict | None) -> dict:
    """One user message in, one reply out. Returns {"reply", "cards"}; cards are the confirmation cards the tools created."""
    owner, role = resolve_workspace(db, actor)
    system = build_prompt(db, owner, actor, role, clean_page(db, owner.id, page), "en")
    tools = [{"type": "function", "function": f} for f in function_definitions()]
    messages = [{"role": "system", "content": system}, *[m for m in history[-MAX_HISTORY:] if m.get("role") in ("user", "assistant")], {"role": "user", "content": text}]
    cards: list[dict] = []
    for _ in range(MAX_ROUNDS):
        message = _chat(messages, tools)
        calls = message.get("tool_calls") or []
        if not calls:
            return {"reply": (message.get("content") or "").strip() or "I have nothing to add.", "cards": cards}
        messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": calls})
        for call in calls:
            fn = call.get("function") or {}
            outcome = run_tool(db, actor, fn.get("name", ""), fn.get("arguments") or {}, clean_page(db, owner.id, page))
            cards.extend(outcome.ui)
            messages.append({"role": "tool", "content": json.dumps(outcome.result, default=str)[:6000]})
    return {"reply": "I could not finish that in a few steps. Try asking in smaller pieces.", "cards": cards}
