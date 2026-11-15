"""Per-account browser identity and proxy parsing.

The identity is generated once at first connect and then reused for every later
login and health check of that account. The user agent matches the real Chromium
build in use; nothing is spoofed or patched.
"""
import random
import re
import sys
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from email_validator import EmailNotValidError, validate_email

VIEWPORTS = ((1366, 768), (1440, 900), (1536, 864), (1920, 1080))
PROXY_SCHEMES = ("http", "https", "socks5")


def _platform_token() -> str:
    if sys.platform == "win32":
        return "Windows NT 10.0; Win64; x64"
    if sys.platform == "darwin":
        return "Macintosh; Intel Mac OS X 10_15_7"
    return "X11; Linux x86_64"


def new_identity(browser_version: str, timezone: str | None) -> dict:
    width, height = random.choice(VIEWPORTS)
    major = browser_version.split(".")[0]
    return {
        "userAgent": f"Mozilla/5.0 ({_platform_token()}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36",
        "viewport": {"width": width, "height": height},
        "locale": "en-US",
        "timezoneId": timezone or "UTC",
    }


def validate_timezone(name: str) -> str:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise ValueError("Unknown timezone") from None
    return name


def validate_proxy_url(url: str) -> str:
    """Accept scheme://[user:pass@]host:port. Error text never echoes the URL."""
    try:
        parts = urlsplit(url.strip())
        valid = parts.scheme in PROXY_SCHEMES and bool(parts.hostname) and parts.port is not None
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Proxy must look like http://host:port, https://host:port or socks5://host:port")
    return url.strip()


def parse_proxy(url: str) -> dict:
    """Convert a validated proxy URL into Playwright's proxy settings."""
    parts = urlsplit(url)
    proxy = {"server": f"{parts.scheme}://{parts.hostname}:{parts.port}"}
    if parts.username:
        proxy["username"] = unquote(parts.username)
        proxy["password"] = unquote(parts.password or "")
    return proxy


PHONE_PATTERN = re.compile(r"^\+[1-9]\d{6,14}$")
IDENTIFIER_HELP = "Enter an email address or a phone number with country code, like +14155550123."


def normalize_identifier(value: str) -> str:
    """Return a lower-cased email or a compact E.164-style phone number."""
    text = value.strip()
    if "@" in text:
        try:
            return validate_email(text, check_deliverability=False).normalized.lower()
        except EmailNotValidError:
            raise ValueError(IDENTIFIER_HELP) from None
    phone = re.sub(r"[\s().-]", "", text)
    if not PHONE_PATTERN.match(phone):
        raise ValueError(IDENTIFIER_HELP)
    return phone
