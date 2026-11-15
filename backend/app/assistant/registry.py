"""The tool registry: the only way the assistant touches Synex data.

A tool is a typed function (pydantic arguments -> JSON schema for the agent), a permission rule (the minimum
workspace role), a kind, and an audit entry on every call. Adding a tool is one ``register(Tool(...))`` in
``tools.py``; nothing here changes.

Kinds
* ``read``  - runs freely, returns data.
* ``draft`` - runs freely, returns text for the user to edit. Nothing is saved or sent.
* ``write`` - never applies. ``propose`` validates and stores a proposal; ``confirm_proposal`` applies it, and
  is reachable only from the signed-in user's click (an HTTP endpoint), never from a tool or the voice session.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from .. import models
from ..deps import ROLE_RANK, resolve_workspace
from ..errors import sanitize_errors
from .config import assistant_config, scrub
from .models import AssistantAudit, AssistantProposal
from .service import get_settings_row

log = logging.getLogger(__name__)


class ToolError(Exception):
    """A problem the user (and the agent) should hear about in plain words."""


@dataclass
class ToolContext:
    db: Session
    actor: models.User          # the signed-in person
    workspace: models.User      # the workspace owner whose data this is
    role: str                   # the actor's role in that workspace
    page: dict = field(default_factory=dict)


@dataclass
class Plan:
    summary: str                # one sentence, plain words
    changes: list[str]          # bullet lines shown on the confirmation card


@dataclass
class Tool:
    name: str
    description: str
    args: type[BaseModel]
    kind: str                   # read | draft | write
    min_role: str               # member | manager | admin
    run: Callable[[ToolContext, Any], dict] | None = None
    propose: Callable[[ToolContext, Any], Plan] | None = None
    apply: Callable[[ToolContext, Any], dict] | None = None


@dataclass
class Outcome:
    result: dict
    ui: list[dict] = field(default_factory=list)


REGISTRY: dict[str, Tool] = {}


def register(tool: Tool) -> Tool:
    if tool.name in REGISTRY:
        raise ValueError(f"Duplicate tool {tool.name}")
    if tool.kind == "write" and not (tool.propose and tool.apply):
        raise ValueError("A write tool needs propose and apply")
    if tool.kind != "write" and not tool.run:
        raise ValueError("A read or draft tool needs run")
    REGISTRY[tool.name] = tool
    return tool


# ------------------------------------------------------------------ schemas for the agent --------------------
def _inline(schema: dict, defs: dict) -> Any:
    if isinstance(schema, list):
        return [_inline(s, defs) for s in schema]
    if not isinstance(schema, dict):
        return schema
    if "$ref" in schema:
        return _inline(defs[schema["$ref"].split("/")[-1]], defs)
    if "anyOf" in schema:  # Optional[X] -> X
        options = [o for o in schema["anyOf"] if o.get("type") != "null"]
        if len(options) == 1:
            merged = {**{k: v for k, v in schema.items() if k not in ("anyOf", "default")}, **_inline(options[0], defs)}
            return merged
    return {k: _inline(v, defs) for k, v in schema.items() if k not in ("title", "$defs", "default")}


def json_schema(tool: Tool) -> dict:
    raw = tool.args.model_json_schema()
    out = _inline(raw, raw.get("$defs", {}))
    out.setdefault("type", "object")
    out.setdefault("properties", {})
    return out


def function_definitions() -> list[dict]:
    return [{"name": t.name, "description": t.description, "parameters": json_schema(t)} for t in REGISTRY.values()]


# ------------------------------------------------------------------ audit ------------------------------------
_PII = {"first_name", "last_name", "email", "phone", "linkedin_url", "company", "job_title", "headline", "location",
        "industry", "notes", "timezone"}
_TEXT = {"message", "body", "text", "instructions", "description", "goal", "audience", "query", "name"}


def minimise(value: Any, key: str = "") -> Any:
    """Arguments as they are stored in the audit log: ids and settings kept; names, contact details and message
    text replaced by a marker or a length."""
    if key in _PII:
        return "[personal data]"
    if isinstance(value, str):
        return f"[{len(value)} chars]" if key in _TEXT or len(value) > 60 else value
    if isinstance(value, dict):
        return {k: minimise(v, k) for k, v in value.items()}
    if isinstance(value, list):
        if value and all(isinstance(v, dict) for v in value):
            if key == "steps":
                return [str(v.get("type")) for v in value]
            return f"[{len(value)} items]"
        return [minimise(v, key) for v in value[:10]]
    return value


def _summarise_result(result: dict) -> str:
    if not isinstance(result, dict):
        return "ok"
    if result.get("ok") is False:
        return scrub(str(result.get("error", "failed")))[:200]
    parts = []
    for k, v in result.items():
        if isinstance(v, list):
            parts.append(f"{k}: {len(v)}")
    return ", ".join(parts) or str(result.get("status", "ok"))


def write_audit(db: Session, workspace_id: str, user_id: str, tool: str, kind: str, args: Any, status: str, result: str | None = None) -> None:
    try:
        db.rollback()
        db.add(AssistantAudit(workspace_id=workspace_id, user_id=user_id, tool=tool, kind=kind, arguments=minimise(args if isinstance(args, dict) else {}),
                              status=status, result=(result or "")[:300] or None, via="assistant"))
        db.commit()
    except Exception as exc:  # an audit failure must not leak a message, and must not hide the tool's own outcome
        log.error("Assistant audit write failed: %s", type(exc).__name__)
        db.rollback()


# ------------------------------------------------------------------ permissions -----------------------------
def _allowed(role: str, min_role: str) -> bool:
    return ROLE_RANK.get(role, 0) >= ROLE_RANK[min_role]


def _denied_message(tool: Tool, role: str) -> str:
    return f"Your role ({role}) does not allow this. It needs a workspace {tool.min_role}. Ask one to do it."


def _errors_text(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(p) for p in e.get('loc', ()))}: {e.get('msg', 'invalid')}" for e in sanitize_errors(exc.errors()))[:400]


def _detail_text(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, list):
        return "; ".join(str(d.get("msg", d)) if isinstance(d, dict) else str(d) for d in detail)[:400]
    return str(detail)[:400]


# ------------------------------------------------------------------ running a tool ---------------------------
def run_tool(db: Session, actor: models.User, name: str, raw_arguments: str | dict | None, page: dict | None = None) -> Outcome:
    """Execute one tool call from the agent on behalf of ``actor``. Never raises: every problem comes back as
    ``{"ok": False, "error": ...}`` for the agent to explain, and every call leaves an audit entry."""
    owner, role = resolve_workspace(db, actor)
    tool = REGISTRY.get(name)
    if tool is None:
        write_audit(db, owner.id, actor.id, name, "system", {}, "invalid", "unknown tool")
        return Outcome({"ok": False, "error": "That is not available yet. The assistant cannot do it."})
    try:
        args_dict = json.loads(raw_arguments) if isinstance(raw_arguments, str) and raw_arguments.strip() else (raw_arguments or {})
        if not isinstance(args_dict, dict):
            raise ValueError("arguments must be an object")
    except ValueError:
        write_audit(db, owner.id, actor.id, name, tool.kind, {}, "invalid", "arguments were not valid JSON")
        return Outcome({"ok": False, "error": "The arguments were not valid JSON."})
    if not get_settings_row(db, owner.id).enabled:
        write_audit(db, owner.id, actor.id, name, tool.kind, args_dict, "denied", "assistant is off for this workspace")
        return Outcome({"ok": False, "error": "The assistant is turned off for this workspace."})
    if not _allowed(role, tool.min_role):
        msg = _denied_message(tool, role)
        write_audit(db, owner.id, actor.id, name, tool.kind, args_dict, "denied", msg)
        return Outcome({"ok": False, "error": msg})
    try:
        args = tool.args.model_validate(args_dict)
    except ValidationError as exc:
        msg = _errors_text(exc)
        write_audit(db, owner.id, actor.id, name, tool.kind, args_dict, "invalid", msg)
        return Outcome({"ok": False, "error": f"Invalid arguments: {msg}"})

    ctx = ToolContext(db=db, actor=actor, workspace=owner, role=role, page=page or {})
    try:
        if tool.kind == "write":
            plan = tool.propose(ctx, args)  # type: ignore[misc]
            proposal = AssistantProposal(
                workspace_id=owner.id, user_id=actor.id, tool=tool.name, arguments=args.model_dump(mode="json"),
                summary=plan.summary, changes=plan.changes,
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=assistant_config.assistant_proposal_ttl_seconds))
            db.add(proposal)
            db.commit()
            write_audit(db, owner.id, actor.id, name, "write", args_dict, "proposed", f"proposal {proposal.id}")
            card = proposal_out(proposal)
            return Outcome(
                {"ok": True, "status": "awaiting_confirmation", "proposalId": proposal.id, "summary": plan.summary,
                 "message": "NOT applied. A confirmation card is on the user's screen; nothing changes until they click Confirm."},
                [{"type": "proposal", "proposal": card}])
        result = tool.run(ctx, args)  # type: ignore[misc]
        ui = result.pop("_ui", []) if isinstance(result, dict) else []
        write_audit(db, owner.id, actor.id, name, tool.kind, args_dict, "ok", _summarise_result(result))
        return Outcome({"ok": True, **result}, ui)
    except ToolError as exc:
        db.rollback()
        write_audit(db, owner.id, actor.id, name, tool.kind, args_dict, "error", str(exc))
        return Outcome({"ok": False, "error": str(exc)})
    except HTTPException as exc:
        db.rollback()
        msg = _detail_text(exc)
        write_audit(db, owner.id, actor.id, name, tool.kind, args_dict, "error", msg)
        return Outcome({"ok": False, "error": msg})
    except Exception as exc:  # never show internals to the agent or the user
        db.rollback()
        log.error("Assistant tool %s failed: %s", name, type(exc).__name__)
        write_audit(db, owner.id, actor.id, name, tool.kind, args_dict, "error", type(exc).__name__)
        return Outcome({"ok": False, "error": "Something went wrong running that. Nothing was changed."})


# ------------------------------------------------------------------ proposals --------------------------------
def proposal_out(p: AssistantProposal) -> dict:
    tool = REGISTRY.get(p.tool)
    return {"id": p.id, "tool": p.tool, "summary": p.summary, "changes": p.changes or [], "status": p.status,
            "needsRole": tool.min_role if tool else "admin",
            "expiresAt": p.expires_at.isoformat() if p.expires_at else None, "result": p.result}


def _load_proposal(db: Session, actor: models.User, proposal_id: str) -> tuple[AssistantProposal, models.User, str]:
    owner, role = resolve_workspace(db, actor)
    p = db.get(AssistantProposal, proposal_id)
    if p is None or p.workspace_id != owner.id or p.user_id != actor.id:
        raise HTTPException(404, "Proposal not found")
    return p, owner, role


def confirm_proposal(db: Session, actor: models.User, proposal_id: str) -> dict:
    """Apply a pending proposal. Called only by the HTTP confirm endpoint, i.e. the user's click."""
    p, owner, role = _load_proposal(db, actor, proposal_id)
    tool = REGISTRY.get(p.tool)
    if p.status != "pending":
        raise HTTPException(409, f"This change was already {p.status}.")
    expires = p.expires_at if p.expires_at.tzinfo else p.expires_at.replace(tzinfo=timezone.utc)
    if expires <= datetime.now(timezone.utc):
        p.status = "expired"
        db.commit()
        raise HTTPException(409, "This proposal expired. Ask the assistant again.")
    if tool is None or tool.kind != "write":
        raise HTTPException(409, "This change is no longer available.")
    if not get_settings_row(db, owner.id).enabled:
        raise HTTPException(403, "The assistant is turned off for this workspace.")
    if not _allowed(role, tool.min_role):
        write_audit(db, owner.id, actor.id, p.tool, "write", p.arguments, "denied", _denied_message(tool, role))
        raise HTTPException(403, _denied_message(tool, role))
    ctx = ToolContext(db=db, actor=actor, workspace=owner, role=role)
    try:
        args = tool.args.model_validate(p.arguments)  # validated again: ceilings and ownership are checked at apply time too
        result = tool.apply(ctx, args)  # type: ignore[misc]
    except (ToolError, HTTPException, ValidationError) as exc:
        db.rollback()
        msg = _errors_text(exc) if isinstance(exc, ValidationError) else (_detail_text(exc) if isinstance(exc, HTTPException) else str(exc))
        p = db.get(AssistantProposal, proposal_id)
        p.status = "failed"
        p.result = {"error": msg}
        db.commit()
        write_audit(db, owner.id, actor.id, p.tool, "write", p.arguments, "failed", msg)
        raise HTTPException(422, msg)
    p = db.get(AssistantProposal, proposal_id)
    p.status = "applied"
    p.result = result
    db.commit()
    write_audit(db, owner.id, actor.id, p.tool, "write", p.arguments, "applied", f"proposal {p.id}")
    return proposal_out(p)


def cancel_proposal(db: Session, actor: models.User, proposal_id: str) -> dict:
    p, owner, _ = _load_proposal(db, actor, proposal_id)
    if p.status != "pending":
        raise HTTPException(409, f"This change was already {p.status}.")
    p.status = "cancelled"
    db.commit()
    write_audit(db, owner.id, actor.id, p.tool, "write", p.arguments, "cancelled", f"proposal {p.id}")
    return proposal_out(p)
