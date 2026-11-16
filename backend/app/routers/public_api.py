"""The public API and the MCP server. Both are authenticated by an API key made in Settings (Authorization: Bearer syx_...).

The public API is small and read-mostly. The MCP server lets an AI client (Claude Desktop and others) use Synex's read and draft tools. Tools that change
data are not offered over MCP, because a confirmation click is needed and an AI client cannot give it.
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import integrations_core as core, models
from ..assistant import tools  # noqa: F401  (registers the tools)
from ..assistant.registry import REGISTRY, function_definitions, run_tool
from ..database import get_db
from ..schemas import LeadIn
from ..serializers import campaign_out, lead_out

router = APIRouter(tags=["public api"])


def api_key_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    header = request.headers.get("authorization", "")
    user = core.user_for_key(db, header[7:].strip() if header.lower().startswith("bearer ") else None)
    if user is None:
        raise HTTPException(401, "A valid API key is required. Send it as 'Authorization: Bearer syx_...'.")
    return user


@router.get("/public/v1/campaigns")
def campaigns(db: Session = Depends(get_db), user: models.User = Depends(api_key_user)):
    return [campaign_out(c) for c in db.query(models.Campaign).filter_by(user_id=user.id).order_by(models.Campaign.created_at.desc()).limit(200)]


@router.get("/public/v1/leads")
def leads(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), db: Session = Depends(get_db), user: models.User = Depends(api_key_user)):
    rows = db.query(models.Lead).filter_by(user_id=user.id).order_by(models.Lead.created_at.desc()).offset(offset).limit(limit).all()
    return {"items": [lead_out(l) for l in rows], "limit": limit, "offset": offset}


@router.post("/public/v1/leads", status_code=201)
def create_lead(body: LeadIn, db: Session = Depends(get_db), user: models.User = Depends(api_key_user)):
    from .leads import _create
    return _create(body, db, user)


@router.get("/public/v1/conversations")
def conversations(needs_reply: bool = False, db: Session = Depends(get_db), user: models.User = Depends(api_key_user)):
    from .inbox import Filters, _page
    total, items = _page(db, user, Filters(needs_reply=needs_reply), 50, 0)
    return {"items": items, "total": total}


# ---- MCP (JSON-RPC 2.0 over HTTP) ----------------------------------------------------------------------------------------

PROTOCOL = "2025-03-26"


def _rpc_error(id_, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def exposed_tools() -> list[dict]:
    return [{"name": f["name"], "description": f["description"], "inputSchema": f["parameters"]} for f in function_definitions() if REGISTRY[f["name"]].kind != "write"]


@router.post("/mcp")
async def mcp(request: Request, db: Session = Depends(get_db), user: models.User = Depends(api_key_user)):
    try:
        message = await request.json()
    except ValueError:
        return JSONResponse(_rpc_error(None, -32700, "Parse error"))
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return JSONResponse(_rpc_error(None, -32600, "Invalid request"))
    id_, method, params = message.get("id"), message.get("method"), message.get("params") or {}
    if method and method.startswith("notifications/"):
        return Response(status_code=202)
    if method == "initialize":
        return JSONResponse({"jsonrpc": "2.0", "id": id_, "result": {"protocolVersion": PROTOCOL, "capabilities": {"tools": {}}, "serverInfo": {"name": "synex", "version": "1"}}})
    if method == "ping":
        return JSONResponse({"jsonrpc": "2.0", "id": id_, "result": {}})
    if method == "tools/list":
        return JSONResponse({"jsonrpc": "2.0", "id": id_, "result": {"tools": exposed_tools()}})
    if method == "tools/call":
        name = params.get("name", "")
        if name not in {t["name"] for t in exposed_tools()}:
            return JSONResponse({"jsonrpc": "2.0", "id": id_, "result": {"content": [{"type": "text", "text": "That tool is not available over MCP. Tools that change data need a confirmation click inside Synex."}], "isError": True}})
        outcome = run_tool(db, user, name, params.get("arguments") or {})
        return JSONResponse({"jsonrpc": "2.0", "id": id_, "result": {"content": [{"type": "text", "text": json.dumps(outcome.result, default=str)}], "isError": not outcome.result.get("ok", True)}})
    return JSONResponse(_rpc_error(id_, -32601, f"Method not found: {method}"))
