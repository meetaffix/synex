"""Environment validation: ``python -m app.check_env`` and the check every server and worker runs at start.

It reports variable NAMES and what is wrong with them, never a value. The one .env lives at the project root
(``config.ENV_FILE``); old per-folder files are reported and ignored.
"""
from __future__ import annotations

import os

if __name__ == "__main__":  # let the checker report a bad DATABASE_URL by name instead of failing while importing the database
    os.environ.setdefault("SYNEX_CHECK_ENV", "1")

import base64
import re
import sys
from dataclasses import dataclass
from urllib.parse import urlsplit

from .assistant.config import AssistantConfig, assistant_config
from .config import ENV_FILE, Settings, settings as default_settings

ERROR, WARN, INFO = "ERROR", "WARN", "info"

# Names that older versions of the project used, and what replaced them.
RENAMED = {
    "DEEPGRAM_APY_KEP": "DEEPGRAM_API_KEY",
    "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY": "VITE_CLERK_PUBLISHABLE_KEY",
    "CLERK_PUBLISHABLE_KEY": "VITE_CLERK_PUBLISHABLE_KEY (the same value serves the backend and the frontend)",
}
REMOVED = {
    "ANTHROPIC_API_KEY": "Deepgram is the only AI provider",
    "ANTHROPIC_MODEL": "Deepgram is the only AI provider",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "Clerk replaces the old token lifetime",
}
# Connection pieces that become DATABASE_URL (see docs/DATABASE.md); not read by the code themselves.
TRANSIENT = {"COCKROACH_SQL_USER", "COCKROACH_SQL_PASSWORD", "COCKROACH_DATABASE", "COCKROACH_CA_CERT", "COCKROACH_HOST"}
SMTP_NAMES = {"SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"}


@dataclass(frozen=True)
class Finding:
    level: str
    name: str
    message: str


def _env_names(path=ENV_FILE) -> set[str]:
    names: set[str] = set()
    try:
        for line in open(path, encoding="utf-8", errors="ignore"):
            match = re.match(r"^\s*([A-Z][A-Z0-9_]*)=", line)  # commented lines are not variables
            if match:
                names.add(match.group(1))
    except OSError:
        pass
    return names


def known_names() -> set[str]:
    names = {n.upper() for n in list(Settings.model_fields) + list(AssistantConfig.model_fields)}
    names |= {"CLERK_PUBLISHABLE_KEY", "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "VITE_CLERK_PUBLISHABLE_KEY", "VITE_API_URL",
              "CLERK_WEBHOOK_SIGNING_SECRET", "OUTREACH_PAGES_FACTORY", "MOCK_LINKEDIN_URL", "SYNEX_ROLE"}
    return names


def validate(s: Settings = default_settings, a: AssistantConfig = assistant_config, names: set[str] | None = None) -> list[Finding]:
    """Every problem found, as findings. ``names`` are the variables present in the .env file (default: read it)."""
    out: list[Finding] = []
    add = lambda level, name, message: out.append(Finding(level, name, message))
    present = _env_names() if names is None else names

    # ---- required
    for name, value in (("SECRET_KEY", s.secret_key), ("ENCRYPTION_KEY", s.encryption_key)):
        if not value:
            add(ERROR, name, "missing: set a random value of at least 32 characters")
        elif len(value) < 32:
            add(ERROR, name, f"too short ({len(value)} characters, needs at least 32)")
    if s.secret_key and s.secret_key == s.encryption_key:
        add(ERROR, "ENCRYPTION_KEY", "must be independent of SECRET_KEY, not the same value")
    url = s.database_url
    scheme = url.split(":", 1)[0].lower()
    if not url:
        add(ERROR, "DATABASE_URL", "missing")
    elif scheme.startswith("sqlite"):
        add(INFO, "DATABASE_URL", "sqlite (fine for local use and unit tests; use CockroachDB or Postgres when hosted)")
    elif scheme.startswith("cockroachdb"):
        parts = urlsplit(url)
        if not parts.password:
            add(ERROR, "DATABASE_URL", "no password in the connection string")
        if "sslmode=verify-full" not in url:
            add(ERROR, "DATABASE_URL", "must use sslmode=verify-full")
        match = re.search(r"sslrootcert=([^&]+)", url)
        if not match:
            add(ERROR, "DATABASE_URL", "needs sslrootcert=<path to the CA certificate>")
        elif not _path_exists(match.group(1)):
            add(ERROR, "DATABASE_URL", "sslrootcert points to a file that does not exist")
    elif scheme.startswith("postgresql"):
        add(ERROR if "cockroach" in url else WARN, "DATABASE_URL", "postgresql:// does not work for CockroachDB: use cockroachdb://")
    else:
        add(ERROR, "DATABASE_URL", f"unsupported scheme {scheme!r} (sqlite, cockroachdb or postgresql)")

    for origin in s.cors_origin_list:
        if not re.fullmatch(r"https?://[^/\s?#]+", origin):
            add(ERROR, "CORS_ORIGINS", "each origin must be scheme://host[:port] with no path or trailing slash")
            break
    if s.cors_origin_regex:
        try:
            re.compile(s.cors_origin_regex)
            if re.search(r"vercel\\?\.app", s.cors_origin_regex) and re.fullmatch(s.cors_origin_regex, "https://evil-site.vercel.app"):
                add(ERROR, "CORS_ORIGIN_REGEX", "matches any Vercel site: scope it to this project's name and team")
        except re.error:
            add(ERROR, "CORS_ORIGIN_REGEX", "is not a valid regular expression")

    # ---- authentication
    provider = s.auth_provider.strip().lower()
    if provider not in ("local", "clerk"):
        add(ERROR, "AUTH_PROVIDER", "must be local or clerk")
    if provider == "clerk":
        if not s.clerk_secret_key.startswith(("sk_test_", "sk_live_")):
            add(ERROR, "CLERK_SECRET_KEY", "missing or not an sk_test_/sk_live_ key")
        host = _clerk_host(s.clerk_publishable_key)
        if host is None:
            add(ERROR, "VITE_CLERK_PUBLISHABLE_KEY", "missing, malformed or not a pk_test_/pk_live_ key (the backend reads the same variable)")
        if s.clerk_webhook_secret and not s.clerk_webhook_secret.startswith("whsec_"):
            add(ERROR, "CLERK_WEBHOOK_SECRET", "must start with whsec_")
        if SMTP_NAMES & present:
            add(INFO, "SMTP_*", "unused while AUTH_PROVIDER=clerk (Clerk sends sign-in and reset emails)")
    else:
        if s.smtp_host and not (1 <= int(s.smtp_port) <= 65535):
            add(ERROR, "SMTP_PORT", "must be a port number")
        if not s.smtp_host:
            add(WARN, "SMTP_HOST", "not set: password-reset email is unavailable with the built-in sign-in")

    # ---- AI
    if a.deepgram_api_key:
        if not re.fullmatch(r"[A-Za-z0-9_\-]{20,}", a.deepgram_api_key):
            add(ERROR, "DEEPGRAM_API_KEY", "does not look like a key (unexpected characters or too short)")
    else:
        add(INFO, "DEEPGRAM_API_KEY", "not set: the assistant and AI drafting are off; template drafts are used")

    # ---- publishing
    linkedin = [bool(s.linkedin_client_id), bool(s.linkedin_client_secret)]
    if any(linkedin) and not all(linkedin):
        add(ERROR, "LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET must be set together")
    if not any(linkedin):
        add(INFO, "LINKEDIN_CLIENT_ID", "not set: content publishing is unavailable")

    # ---- deployment
    if s.cookie_secure and not s.frontend_url.startswith("https://"):
        add(WARN, "FRONTEND_URL", "COOKIE_SECURE is true but FRONTEND_URL is not https")

    # ---- database connection budget (managed plans allow few connections; see docs/DATABASE.md)
    if not scheme.startswith("sqlite"):
        from .database import connection_budget
        used, limit = connection_budget(s)
        if used > limit:
            add(ERROR, "DB_POOL_*", f"pools allow {used} connections across the API and workers; the budget is {limit}")

    # ---- names in the file
    known = known_names()
    for name in sorted(present):
        if name in RENAMED:
            add(WARN, name, f"old name: use {RENAMED[name]}")
        elif name in REMOVED:
            add(WARN, name, f"no longer read ({REMOVED[name]}): remove it")
        elif name in TRANSIENT:
            add(WARN, name, "not read by the code: build DATABASE_URL from it, then remove it")
        elif name not in known:
            add(WARN, name, "not read by any code: misspelt or unused")
    for old in (ENV_FILE.parent / "backend" / ".env", ENV_FILE.parent / "frontend" / ".env"):
        if old.exists():
            add(WARN, str(old.relative_to(ENV_FILE.parent)), "an old per-folder env file: it is ignored, move anything needed to the root .env")
    if not ENV_FILE.exists():
        add(WARN, ".env", "the root .env file does not exist (environment variables may still come from the host)")
    return out


def _path_exists(path: str) -> bool:
    from pathlib import Path
    from urllib.parse import unquote
    return Path(unquote(path)).exists()


def _clerk_host(key: str) -> str | None:
    if not key.startswith(("pk_test_", "pk_live_")):
        return None
    body = key.split("_", 2)[2]
    try:
        host = base64.b64decode(body + "=" * (-len(body) % 4)).decode().rstrip("$")
    except Exception:  # noqa: BLE001
        return None
    return host if "." in host else None


def render(findings: list[Finding]) -> str:
    width = max([len(f.name) for f in findings] + [4])
    lines = [f"{f.level:<5}  {f.name:<{width}}  {f.message}" for f in findings]
    errors = sum(f.level == ERROR for f in findings)
    warns = sum(f.level == WARN for f in findings)
    lines.append(f"{errors} error(s), {warns} warning(s). Values are never printed.")
    return "\n".join(lines)


def require_valid_env(who: str = "Synex") -> None:
    """Called when a server or worker starts: stop with the names of what is wrong, never the values."""
    errors = [f for f in validate() if f.level == ERROR]
    if errors:
        raise SystemExit(f"{who} cannot start: fix these environment variables (python -m app.check_env shows all of them):\n" +
                         "\n".join(f"  {f.name}: {f.message}" for f in errors))


def main() -> int:
    findings = validate()
    print(render(findings))
    return 1 if any(f.level == ERROR for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
