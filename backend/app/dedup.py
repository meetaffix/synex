"""Canonical keys for de-duplicating leads across import sources."""

from __future__ import annotations

import re

_PUBLIC_ID_RE = re.compile(r"/in/([^/?#]+)", re.I)


def normalize_linkedin_url(url: str | None) -> str:
    """Collapse a LinkedIn profile URL to a stable key.

    Handles the variants that otherwise create duplicate leads: scheme,
    query/fragment (tracking params), trailing slash, and host variants
    (``m``/``mw``/``mwlite``/``www`` and country subdomains like
    ``in.linkedin.com``). When the URL carries the canonical
    ``/in/{publicId}`` slug we key on that alone — it is the one identifier
    LinkedIn keeps stable across every surface.
    """
    if not url:
        return ""
    u = url.strip().lower()
    m = _PUBLIC_ID_RE.search(u)
    if m:
        return f"linkedin.com/in/{m.group(1)}"
    u = u.split("?")[0].split("#")[0].rstrip("/")
    u = re.sub(r"^https?://", "", u)
    # Collapse any country/mobile host prefix down to the bare domain.
    u = re.sub(r"^(?:[a-z]{2,3}\.)?(?:m|mw|mwlite|www)\.linkedin\.com", "linkedin.com", u)
    u = re.sub(r"^(?:[a-z]{2,3}\.)linkedin\.com", "linkedin.com", u)
    return u


def lead_dedup_key(
    first_name: str | None,
    last_name: str | None,
    company: str | None,
    linkedin_url: str | None,
) -> str:
    """Best available dedup key.

    Prefers the normalized LinkedIn URL; falls back to a name+company composite
    so URL-less CSV rows don't slip in as duplicates. Returns ``""`` when there
    is nothing reliable to dedupe on (no URL and no name).
    """
    n = normalize_linkedin_url(linkedin_url)
    if n:
        return f"url:{n}"
    name = f"{(first_name or '').strip().lower()} {(last_name or '').strip().lower()}".strip()
    if name:
        return f"nc:{name}|{(company or '').strip().lower()}"
    return ""
