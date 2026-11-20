"""The relay: browser <-> Synex backend <-> Deepgram Voice Agent.

The browser talks only to this backend, over a WebSocket it opens with a single-use ticket. This backend opens the
Deepgram connection with DEEPGRAM_API_KEY, so the key never leaves the server, and the cap, the idle timeout and
every tool call are enforced here, where the browser cannot skip them.

Browser -> server: binary frames = microphone audio (16 kHz linear16). JSON: user_text, activity, context, note, end.
Server -> browser: binary frames = agent speech (24 kHz linear16). JSON: ready, transcript, user_speaking, thinking,
agent_audio_done, tool, proposal, draft, usage, error, closed.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field

from fastapi import WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from websockets.asyncio.client import connect

from ..database import SessionLocal
from .. import models
from ..deps import resolve_workspace
from .config import assistant_config, scrub
from .models import AssistantMessage, AssistantProposal
from .prompt import build_prompt, build_settings, clean_page
from .registry import run_tool
from .service import Ticket, add_usage, effective_minutes, get_settings_row, used_seconds

log = logging.getLogger(__name__)

TICK_SECONDS = 1.0        # how often the idle and cap checks run (tests shorten it)
USAGE_SECONDS = 15.0      # how often usage is saved and reported
KEEPALIVE_SECONDS = 5.0   # Deepgram closes a silent connection, and a typing session sends no audio
SETTINGS_TIMEOUT = 15.0
MAX_TEXT = 2000


class Refused(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass
class Prepared:
    settings: dict
    idle: int
    cap_seconds: float
    used_before: float
    history: bool
    language: str
    mode: str
    page: dict
    last_activity: float = field(default_factory=time.monotonic)
    started: float = field(default_factory=time.monotonic)
    flushed_to: float = field(default_factory=time.monotonic)
    injected: deque = field(default_factory=lambda: deque(maxlen=20))

    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def used_now(self) -> float:
        return self.used_before + self.elapsed()


def _prepare(ticket: Ticket) -> Prepared:
    with SessionLocal() as db:
        actor = db.get(models.User, ticket.user_id)
        if actor is None:
            raise Refused("not_signed_in", "Your account was not found. Sign in again.")
        owner, role = resolve_workspace(db, actor)
        if owner.id != ticket.workspace_id:
            raise Refused("not_allowed", "Your workspace changed. Open the assistant again.")
        row = get_settings_row(db, owner.id)
        if not row.enabled:
            raise Refused("disabled", "The assistant is turned off for this workspace.")
        used = used_seconds(db, owner.id)
        minutes = effective_minutes(db, owner.id, row)
        cap = minutes * 60
        if used >= cap:
            raise Refused("cap_reached", f"This workspace has used its {minutes} assistant minutes for the month.")
        language = ticket.language if ticket.language in ("en", "en-IN") else row.language
        page = clean_page(db, owner.id, ticket.page)
        prompt = build_prompt(db, owner, actor, role, page, language)
        return Prepared(build_settings(prompt, ticket.mode, language), row.idle_timeout_seconds, cap, used, row.history_enabled, language, ticket.mode, page)


def _execute(user_id: str, name: str, arguments: str, page: dict):
    with SessionLocal() as db:
        actor = db.get(models.User, user_id)
        return run_tool(db, actor, name, arguments, page)


def _store_line(ws_id: str, user_id: str, session_id: str, role: str, text: str) -> None:
    with SessionLocal() as db:
        db.add(AssistantMessage(workspace_id=ws_id, user_id=user_id, session_id=session_id, role=role, text=text[:4000]))
        db.commit()


def _flush(ws_id: str, seconds: float) -> None:
    with SessionLocal() as db:
        add_usage(db, ws_id, seconds)


def _rebuild_prompt(ticket: Ticket, page: dict, language: str) -> tuple[str, dict]:
    with SessionLocal() as db:
        actor = db.get(models.User, ticket.user_id)
        owner, role = resolve_workspace(db, actor)
        clean = clean_page(db, owner.id, page)
        return build_prompt(db, owner, actor, role, clean, language), clean


def _note(ticket: Ticket, proposal_id: str) -> str | None:
    """What the user just did to a proposal, taken from the database (never from what the browser claims)."""
    with SessionLocal() as db:
        p = db.get(AssistantProposal, proposal_id)
        if p is None or p.user_id != ticket.user_id or p.status not in ("applied", "cancelled", "failed"):
            return None
        return {"applied": f"I pressed Confirm and it was applied: {p.summary}",
                "cancelled": f"I cancelled it: {p.summary}",
                "failed": f"I pressed Confirm but it could not be applied: {(p.result or {}).get('error', 'unknown reason')}"}[p.status]


async def run_relay(client: WebSocket, ticket: Ticket) -> None:
    cfg = assistant_config
    out_lock = asyncio.Lock()

    async def to_client(message: dict) -> None:
        async with out_lock:
            await client.send_text(json.dumps(message))

    try:
        prep: Prepared = await run_in_threadpool(_prepare, ticket)
    except Refused as exc:
        await to_client({"type": "error", "code": exc.code, "message": exc.message})
        await to_client({"type": "closed", "reason": exc.code})
        return
    if not cfg.deepgram_api_key:
        await to_client({"type": "error", "code": "unavailable", "message": "The voice service is not configured on this server."})
        await to_client({"type": "closed", "reason": "unavailable"})
        return

    reason = "ended"
    try:
        async with connect(cfg.deepgram_agent_url, additional_headers={"Authorization": f"Token {cfg.deepgram_api_key}"},
                           max_size=None, open_timeout=15) as dg:
            await dg.send(json.dumps(prep.settings))
            await _await_settings_applied(dg)
            prep.started = prep.flushed_to = prep.last_activity = time.monotonic()
            await to_client({"type": "ready", "mode": prep.mode, "language": prep.language, "idleTimeoutSeconds": prep.idle,
                             "remainingSeconds": max(0, round(prep.cap_seconds - prep.used_before))})
            calls: set[asyncio.Task] = set()

            async def flush_usage() -> None:
                now = time.monotonic()
                seconds, prep.flushed_to = now - prep.flushed_to, now
                await run_in_threadpool(_flush, ticket.workspace_id, seconds)

            async def handle_call(call: dict) -> None:
                name = str(call.get("name", ""))
                await to_client({"type": "tool", "name": name, "status": "running"})
                outcome = await run_in_threadpool(_execute, ticket.user_id, name, call.get("arguments", "{}"), prep.page)
                for event in outcome.ui:
                    await to_client(event)
                await to_client({"type": "tool", "name": name, "status": "done" if outcome.result.get("ok") else "failed"})
                prep.last_activity = time.monotonic()
                await dg.send(json.dumps({"type": "FunctionCallResponse", "id": call.get("id"), "name": name,
                                          "content": json.dumps(outcome.result, default=str)[:8000]}))

            async def upstream_to_client() -> str:
                async for raw in dg:
                    if isinstance(raw, bytes):
                        async with out_lock:
                            await client.send_bytes(raw)
                        continue
                    try:
                        msg = json.loads(raw)
                    except ValueError:
                        continue
                    kind = msg.get("type")
                    if kind == "ConversationText":
                        role, text = msg.get("role", "assistant"), str(msg.get("content", ""))
                        if role == "user" and prep.injected and prep.injected[0] == text:
                            prep.injected.popleft()  # our own typed message coming back: the browser already has it
                            continue
                        if role == "user":
                            prep.last_activity = time.monotonic()
                        if prep.history and text:
                            await run_in_threadpool(_store_line, ticket.workspace_id, ticket.user_id, ticket.session_id, role, text)
                        await to_client({"type": "transcript", "role": role, "text": text})
                    elif kind == "UserStartedSpeaking":
                        prep.last_activity = time.monotonic()
                        await to_client({"type": "user_speaking"})
                    elif kind == "AgentThinking":
                        await to_client({"type": "thinking"})
                    elif kind == "AgentAudioDone":
                        await to_client({"type": "agent_audio_done"})
                    elif kind == "FunctionCallRequest":
                        for call in msg.get("functions", []):
                            if call.get("client_side", True):
                                task = asyncio.create_task(handle_call(call))
                                calls.add(task)
                                task.add_done_callback(calls.discard)
                    elif kind == "Error":
                        log.warning("Deepgram agent error code=%s", str(msg.get("code", ""))[:40])
                        await to_client({"type": "error", "code": "agent_error", "message": scrub(str(msg.get("description", "The voice service reported an error.")))[:200]})
                return "upstream_closed"

            async def client_to_upstream() -> str:
                while True:
                    event = await client.receive()
                    if event["type"] == "websocket.disconnect":
                        return "client_closed"
                    if event.get("bytes") is not None:
                        if prep.mode == "voice":
                            await dg.send(event["bytes"])
                        continue
                    try:
                        msg = json.loads(event.get("text") or "")
                    except ValueError:
                        continue
                    kind = msg.get("type")
                    if kind == "user_text":
                        text = str(msg.get("text", "")).strip()[:MAX_TEXT]
                        if text:
                            prep.last_activity = time.monotonic()
                            prep.injected.append(text)
                            if prep.history:
                                await run_in_threadpool(_store_line, ticket.workspace_id, ticket.user_id, ticket.session_id, "user", text)
                            await to_client({"type": "transcript", "role": "user", "text": text, "typed": True})
                            await dg.send(json.dumps({"type": "InjectUserMessage", "content": text}))
                    elif kind == "activity":
                        prep.last_activity = time.monotonic()
                    elif kind == "context":
                        prompt, page = await run_in_threadpool(_rebuild_prompt, ticket, msg.get("page") or {}, prep.language)
                        if page != prep.page:
                            prep.page = page
                            await dg.send(json.dumps({"type": "UpdatePrompt", "prompt": prompt}))
                    elif kind == "note" and isinstance(msg.get("proposalId"), str):
                        text = await run_in_threadpool(_note, ticket, msg["proposalId"])
                        if text:
                            prep.last_activity = time.monotonic()
                            await dg.send(json.dumps({"type": "InjectUserMessage", "content": text}))
                    elif kind == "end":
                        return "ended"

            async def keepalive() -> str:
                while True:
                    await asyncio.sleep(KEEPALIVE_SECONDS)
                    await dg.send(json.dumps({"type": "KeepAlive"}))

            async def watchdog() -> str:
                last_report = time.monotonic()
                while True:
                    await asyncio.sleep(TICK_SECONDS)
                    now = time.monotonic()
                    if prep.used_now() >= prep.cap_seconds:
                        return "cap_reached"
                    if now - prep.last_activity >= prep.idle:
                        return "idle"
                    if now - last_report >= USAGE_SECONDS:
                        last_report = now
                        await flush_usage()
                        await to_client({"type": "usage", "remainingSeconds": max(0, round(prep.cap_seconds - prep.used_now())),
                                         "idleInSeconds": max(0, round(prep.idle - (now - prep.last_activity)))})

            tasks = [asyncio.create_task(f()) for f in (upstream_to_client, client_to_upstream, keepalive, watchdog)]
            try:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for t in done:
                    exc = t.exception()
                    if exc is not None and not isinstance(exc, (WebSocketDisconnect, asyncio.CancelledError)):
                        log.warning("Assistant relay ended: %s", type(exc).__name__)
                        reason = "error"
                    elif exc is None:
                        reason = t.result()
                    else:
                        reason = "client_closed"
            finally:
                for t in [*tasks, *calls]:
                    t.cancel()
                await asyncio.gather(*tasks, *calls, return_exceptions=True)
                await flush_usage()
    except Refused as exc:
        reason = exc.code
        await _safely(to_client, {"type": "error", "code": exc.code, "message": exc.message})
    except Exception as exc:  # never put the exception text in a log or a message: it can carry request details
        log.error("Assistant connection to Deepgram failed: %s", type(exc).__name__)
        reason = "upstream_unavailable"
        await _safely(to_client, {"type": "error", "code": "upstream_unavailable", "message": "The voice service could not be reached. Try again in a moment."})
    if reason != "client_closed":
        await _safely(to_client, {"type": "closed", "reason": reason})


async def _await_settings_applied(dg) -> None:
    async def wait() -> None:
        async for raw in dg:
            if isinstance(raw, bytes):
                continue
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if msg.get("type") == "SettingsApplied":
                return
            if msg.get("type") == "Error":
                log.warning("Deepgram rejected the agent settings: code=%s", str(msg.get("code", ""))[:40])
                raise Refused("agent_error", "The voice service did not accept the assistant's configuration.")
        raise Refused("upstream_unavailable", "The voice service closed the connection.")
    try:
        await asyncio.wait_for(wait(), SETTINGS_TIMEOUT)
    except asyncio.TimeoutError:
        raise Refused("upstream_unavailable", "The voice service did not answer in time.")


async def _safely(fn, *args) -> None:
    try:
        await fn(*args)
    except Exception:
        pass
