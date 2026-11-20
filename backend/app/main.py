import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .config import settings
from .errors import sanitize_errors
from .migrations import migrate
from .routers import auth, leads, lead_lists, campaigns, conversations, templates, settings as settings_router, ai, team, accounts, reconnect, outreach, assistant, clerk, drafts, dashboard, lead_collections, do_not_contact, company_lists, inbox, integrations, public_api, voice_notes, post_reviews, engagement, plan, audit
from .linkedin_session import shutdown_manager
from . import linkedin, publishing, images

@asynccontextmanager
async def lifespan(app):
    from .check_env import require_valid_env
    require_valid_env("The API")  # names of what is wrong, never values
    migrate()
    yield
    shutdown_manager()

app = FastAPI(title="SYNEX API", version="2.0.0", lifespan=lifespan)
class SettingsCORSMiddleware(CORSMiddleware):
    """CORS that asks ``settings.origin_allowed`` on every request, so the listed origins and the optional
    project-specific regex are the same set the write check and Clerk's authorized parties use."""

    def is_allowed_origin(self, origin: str) -> bool:
        return settings.origin_allowed(origin)


app.add_middleware(SettingsCORSMiddleware, allow_origins=settings.cors_origin_list,
                   allow_credentials=True, allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"], allow_headers=["Content-Type", "Authorization"])
_attempts = defaultdict(deque)
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
UPLOAD_PATHS = ("/voice-notes", "/images", "/leads", "/publishing", "/assistant", "/integrations/import", "/do-not-contact", "/lead-collections")

@app.middleware("http")
async def safeguards(request: Request, call_next):
    path = request.url.path
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        # A request is refused before it is read when it claims to be too big. Uploads (pictures, voice notes, CSV files) may be larger.
        limit = MAX_UPLOAD_BYTES if path.startswith(UPLOAD_PATHS) else MAX_BODY_BYTES
        if int(request.headers.get("content-length") or 0) > limit:
            return JSONResponse({"detail": f"That request is too large. The most this endpoint takes is {limit // (1024 * 1024)} MB."}, status_code=413)
        origin = request.headers.get("origin")
        if (origin and not settings.origin_allowed(origin)) or (request.cookies.get("synex_session") and not origin):
            return JSONResponse({"detail": "Request origin is not allowed"}, status_code=403)
        if path == "/auth":
            key = request.client.host if request.client else "unknown"
            now = time.monotonic()
            # Bounded local limiter. Use a shared edge limit for multi-instance deployments.
            if len(_attempts) > 10000:
                _attempts.clear()
            queue = _attempts[key]
            while queue and queue[0] < now - 60:
                queue.popleft()
            if len(queue) >= 20:
                return JSONResponse({"detail": "Too many attempts. Try again in a minute."}, status_code=429)
            queue.append(now)
        if path in ("/leads", "/campaigns", "/conversations"):
            try:
                body = await request.json()
            except Exception:
                body = {}
            if not isinstance(body, dict):
                return JSONResponse({"detail": "Expected an object"}, status_code=422)
            action = body.get("action")
            unsupported = (path == "/conversations" and action == "compose") or (path == "/leads" and (action in ("enrich", "enrich-all") or (action == "import" and body.get("source") != "csv")))
            if unsupported:
                return JSONResponse({"detail": "This action is not available through this app's official LinkedIn API access. Use a manual LinkedIn workflow."}, status_code=409)
    response = await call_next(request)
    if path == "/linkedin/callback":
        request.scope["query_string"] = b""  # Never put authorization codes in access logs.
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response

for router in (engagement.router, post_reviews.router, voice_notes.router, auth.router, leads.router, lead_lists.router, campaigns.router, conversations.router, templates.router, settings_router.router, ai.router, team.router, accounts.router, reconnect.router, outreach.router, linkedin.router, publishing.router, images.router, assistant.router, clerk.router, drafts.router, dashboard.router, lead_collections.router, do_not_contact.router, company_lists.router, inbox.router, integrations.router, public_api.router, plan.router, audit.router):
    app.include_router(router)

@app.get("/health")
def health():
    return {"status": "ok"}

from sqlalchemy.exc import IntegrityError
@app.exception_handler(IntegrityError)
async def conflict_handler(request, exc):
    return JSONResponse({"detail": "This record conflicts with an existing record. Refresh and try again."}, status_code=409)


@app.exception_handler(RequestValidationError)
async def validation_handler(request, exc):
    """A 422 describes what is wrong, never the values sent: they may be passwords or tokens."""
    return JSONResponse({"detail": sanitize_errors(exc.errors())}, status_code=422)
