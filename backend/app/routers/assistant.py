"""Assistant API: settings and usage, starting a session, confirming or cancelling a proposal, history, audit.

Starting a session returns a single-use ticket (30 s) for the relay WebSocket. The Deepgram API key stays on the
server; see ``app/assistant/relay.py``.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, WebSocket
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..assistant import registry, service
from ..assistant.config import LANGUAGES, assistant_config
from ..assistant.models import AssistantAudit, AssistantMessage
from ..assistant.prompt import clean_page
from ..assistant.relay import run_relay
from ..config import settings
from ..database import get_db
from ..deps import get_current_user, require_role, resolve_workspace
from .. import models

router = APIRouter(prefix="/assistant", tags=["assistant"])


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool | None = None
    monthly_minute_cap: int | None = Field(None, alias="monthlyMinuteCap", ge=0, le=10000)
    idle_timeout_seconds: int | None = Field(None, alias="idleTimeoutSeconds", ge=30, le=1800)
    history_enabled: bool | None = Field(None, alias="historyEnabled")
    language: Literal["en", "en-IN"] | None = None
    provider: Literal["deepgram", "local"] | None = None


class SessionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["voice", "text"] = "text"
    page: dict = Field(default_factory=dict)


@router.get("/settings")
def get_assistant_settings(db: Session = Depends(get_db), actor: models.User = Depends(get_current_user)):
    owner, role = resolve_workspace(db, actor)
    return service.settings_out(db, owner.id, can_edit=role == "admin")


@router.put("/settings")
def update_assistant_settings(body: SettingsIn, db: Session = Depends(get_db), actor: models.User = Depends(get_current_user)):
    owner = require_role(db, actor, "admin")
    row = service.get_settings_row(db, owner.id)
    if body.provider == "local":
        from ..assistant import local
        ready = local.available()
        if not (ready["reachable"] and ready["installed"]):
            raise HTTPException(409, "The local language model is not ready, so the assistant cannot switch to it. Start Ollama and pull the model first (see the Local models card).")
    for field, value in (("enabled", body.enabled), ("monthly_minute_cap", body.monthly_minute_cap), ("idle_timeout_seconds", body.idle_timeout_seconds),
                         ("history_enabled", body.history_enabled), ("language", body.language), ("provider", body.provider)):
        if value is not None:
            setattr(row, field, value)
    db.commit()
    return service.settings_out(db, owner.id, can_edit=True)


@router.post("/session")
def start_session(body: SessionIn, db: Session = Depends(get_db), actor: models.User = Depends(get_current_user)):
    owner, _ = resolve_workspace(db, actor)
    out = service.settings_out(db, owner.id, can_edit=False)
    if not out["enabled"]:
        raise HTTPException(403, "The assistant is turned off for this workspace. An admin can turn it on in Settings.")
    if out["provider"] == "local":
        raise HTTPException(409, "The assistant is set to local models, which answer through /assistant/local/chat and need no Deepgram session.")
    if not out["available"]:
        raise HTTPException(503, "The assistant is not set up on this server yet. Ask whoever runs Synex to add the voice service key.")
    if out["capReached"]:
        raise HTTPException(429, f"This workspace has used its {out['monthlyMinuteCap']} assistant minutes for {out['month']}. An admin can raise the cap in Settings, or it resets next month.")
    ticket = service.issue_ticket(actor.id, owner.id, body.mode, out["language"], clean_page(db, owner.id, body.page))
    return {
        "ticket": ticket,
        "wsPath": "/assistant/ws",
        "ticketExpiresInSeconds": assistant_config.assistant_ticket_ttl_seconds,
        "mode": body.mode,
        "language": out["language"],
        "idleTimeoutSeconds": out["idleTimeoutSeconds"],
        "remainingSeconds": out["remainingSeconds"],
        "agent": {"model": out["model"], "voice": out["voice"], "inputSampleRate": 16000, "outputSampleRate": 24000, "encoding": "linear16"},
        "historyEnabled": out["historyEnabled"],
    }


@router.post("/proposals/{proposal_id}/confirm")
def confirm(proposal_id: str, db: Session = Depends(get_db), actor: models.User = Depends(get_current_user)):
    return registry.confirm_proposal(db, actor, proposal_id)


@router.post("/proposals/{proposal_id}/cancel")
def cancel(proposal_id: str, db: Session = Depends(get_db), actor: models.User = Depends(get_current_user)):
    return registry.cancel_proposal(db, actor, proposal_id)


@router.get("/history")
def history(db: Session = Depends(get_db), actor: models.User = Depends(get_current_user)):
    owner, _ = resolve_workspace(db, actor)
    rows = (db.query(AssistantMessage).filter_by(workspace_id=owner.id, user_id=actor.id)
            .order_by(AssistantMessage.created_at.desc()).limit(200).all())
    return [{"role": r.role, "text": r.text, "at": r.created_at.isoformat()} for r in reversed(rows)]


@router.delete("/history", status_code=204)
def clear_history(db: Session = Depends(get_db), actor: models.User = Depends(get_current_user)):
    owner, _ = resolve_workspace(db, actor)
    db.query(AssistantMessage).filter_by(workspace_id=owner.id, user_id=actor.id).delete()
    db.commit()


@router.get("/audit")
def audit(db: Session = Depends(get_db), actor: models.User = Depends(get_current_user)):
    owner = require_role(db, actor, "admin")
    rows = db.query(AssistantAudit).filter_by(workspace_id=owner.id).order_by(AssistantAudit.created_at.desc()).limit(100).all()
    return [{"id": r.id, "userId": r.user_id, "tool": r.tool, "kind": r.kind, "arguments": r.arguments, "status": r.status,
             "result": r.result, "via": r.via, "at": r.created_at.isoformat()} for r in rows]


@router.websocket("/ws")
async def assistant_socket(websocket: WebSocket):
    origin = websocket.headers.get("origin")
    if origin and not settings.origin_allowed(origin):
        await websocket.close(code=4403)
        return
    await websocket.accept()
    ticket = None
    try:
        import asyncio
        import json
        first = json.loads(await asyncio.wait_for(websocket.receive_text(), 10))
        if first.get("type") == "auth" and isinstance(first.get("ticket"), str):
            ticket = service.redeem_ticket(first["ticket"])
    except Exception:
        ticket = None
    if ticket is None:
        await websocket.send_text('{"type":"error","code":"bad_ticket","message":"This assistant session expired. Open the assistant again."}')
        await websocket.close(code=4401)
        return
    if not service.session_started(ticket.workspace_id):
        await websocket.send_text('{"type":"error","code":"busy","message":"Too many assistant sessions are open in this workspace."}')
        await websocket.close(code=4429)
        return
    try:
        await run_relay(websocket, ticket)
    finally:
        service.session_ended(ticket.workspace_id)
        try:
            await websocket.close()
        except Exception:
            pass


class LocalChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=2000)
    history: list[dict] = Field(default_factory=list, max_length=40)
    page: dict = Field(default_factory=dict)


@router.get("/providers")
def provider_choices(db: Session = Depends(get_db), actor: models.User = Depends(get_current_user)):
    """What the assistant can run on, whether each is ready, and the one in use."""
    from ..assistant import speech
    owner, _ = resolve_workspace(db, actor)
    return {"selected": service.get_settings_row(db, owner.id).provider or "deepgram", "providers": speech.providers()}


class SpeechIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    audio: str = Field(max_length=4_000_000)  # a base64 .wav of up to 60 seconds


class SpeakIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=4000)


@router.post("/local/transcribe")
def local_transcribe(body: SpeechIn, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Whisper on this computer: a recording in, the words out. Nothing is stored."""
    import base64
    import binascii

    from ..assistant import speech
    try:
        data = base64.b64decode(body.audio, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "The recording could not be read. Try again.")
    try:
        return {"text": speech.transcribe(data)}
    except speech.SpeechError as exc:
        raise HTTPException(422, str(exc))


@router.post("/local/speak")
def local_speak(body: SpeakIn, user: models.User = Depends(get_current_user)):
    """Piper on this computer: a reply in, a .wav voice out."""
    from fastapi.responses import Response

    from ..assistant import speech
    try:
        return Response(speech.speak(body.text), media_type="audio/wav")
    except speech.SpeechError as exc:
        raise HTTPException(422, str(exc))


@router.get("/local/status")
def local_status(user: models.User = Depends(get_current_user)):
    """Whether the free local-model option is ready, for the settings screen."""
    from ..assistant import local
    return local.available()


@router.post("/local/chat")
def local_chat(body: LocalChatIn, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """A typed conversation answered by a local model (Ollama). Same tools, permissions, audit and confirmation cards as the voice assistant."""
    from ..assistant import local
    owner, _ = resolve_workspace(db, user)
    if not service.get_settings_row(db, owner.id).enabled:
        raise HTTPException(403, "The assistant is turned off for this workspace.")
    try:
        return local.chat(db, user, body.text, body.history, body.page)
    except local.LocalAssistantError as exc:
        raise HTTPException(503, str(exc))
