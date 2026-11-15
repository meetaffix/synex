"""One-shot text completion through Deepgram's Voice Agent, the only AI service Synex uses.

Drafting and post-editing need one short answer, not a conversation, so this opens a Voice Agent connection, sends
one InjectUserMessage, collects the agent's written reply (the spoken audio is discarded) and closes. The key
comes from backend/.env through ``assistant_config`` and never appears in an error message (see ``scrub``).
Any failure raises ``DeepgramTextError``; callers fall back to the local template draft.
"""
from __future__ import annotations

import json
import logging

from websockets.exceptions import WebSocketException
from websockets.sync.client import connect

from .assistant.config import assistant_config, scrub

log = logging.getLogger(__name__)


class DeepgramTextError(RuntimeError):
    pass


def _settings(system_prompt: str) -> dict:
    cfg = assistant_config
    return {
        "type": "Settings",
        "tags": ["synex-drafting"],
        "mip_opt_out": True,
        "audio": {"input": {"encoding": "linear16", "sample_rate": 16000},
                  "output": {"encoding": "linear16", "sample_rate": 24000, "container": "none"}},
        "agent": {
            "listen": {"provider": {"type": "deepgram", "version": "v1", "model": cfg.assistant_stt_model, "language": "en", "smart_format": True}},
            "think": {"provider": {"type": cfg.assistant_llm_provider, "model": cfg.assistant_llm_model}, "prompt": system_prompt},
            "speak": {"provider": {"type": "deepgram", "model": cfg.assistant_voice}},
        },
    }


def complete(system_prompt: str, user_text: str, timeout: float = 25.0) -> str:
    """The agent's written reply to ``user_text``. Raises DeepgramTextError on any problem."""
    cfg = assistant_config
    if not cfg.deepgram_api_key:
        raise DeepgramTextError("Deepgram is not configured.")
    try:
        with connect(cfg.deepgram_agent_url, additional_headers={"Authorization": f"Token {cfg.deepgram_api_key}"},
                     open_timeout=timeout, close_timeout=2, max_size=2**22) as ws:
            _wait_for(ws, "Welcome", timeout)
            ws.send(json.dumps(_settings(system_prompt)))
            _wait_for(ws, "SettingsApplied", timeout)
            ws.send(json.dumps({"type": "InjectUserMessage", "content": user_text}))
            parts = _collect(ws, timeout)
    except DeepgramTextError:
        raise
    except (OSError, WebSocketException, TimeoutError, ValueError) as exc:
        raise DeepgramTextError(scrub(f"Deepgram request failed: {type(exc).__name__}")) from None
    text = " ".join(p.strip() for p in parts if p.strip()).strip()
    if not text:
        raise DeepgramTextError("Deepgram returned an empty reply.")
    return text


def _wait_for(ws, kind: str, timeout: float) -> None:
    while True:
        message = ws.recv(timeout=timeout)
        if isinstance(message, bytes):
            continue
        data = json.loads(message)
        if data.get("type") == kind:
            return
        if data.get("type") == "Error":
            raise DeepgramTextError(scrub(f"Deepgram refused the request: {data.get('description') or data.get('code') or 'error'}"))


def _collect(ws, timeout: float) -> list[str]:
    parts: list[str] = []
    while True:
        message = ws.recv(timeout=timeout)
        if isinstance(message, bytes):
            continue  # the spoken version of the reply is not wanted
        data = json.loads(message)
        kind = data.get("type")
        if kind == "ConversationText" and data.get("role") == "assistant":
            parts.append(str(data.get("content", "")))
        elif kind == "AgentAudioDone":
            return parts
        elif kind == "Error":
            raise DeepgramTextError(scrub(f"Deepgram reported an error: {data.get('description') or data.get('code') or 'error'}"))
