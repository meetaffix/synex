"""Reading people out of LinkedIn pages for lead import (read only: nothing is clicked except what opens a list).

The page text is parsed by shape, not by LinkedIn's generated class names: every link to /in/<id> is walked up to its result
card, and the card's lines give name, connection degree, headline and location. This is more robust than class selectors,
but it has only been exercised against the local mock site. UNVERIFIED on real LinkedIn until captured (see the handover).
"""
from __future__ import annotations

import asyncio
import random
import re
from collections.abc import Awaitable, Callable
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

from playwright.async_api import Page

from ..dedup import normalize_linkedin_url

CARD_JS = r"""
() => {
  const out = [];
  const seen = new Set();
  for (const a of document.querySelectorAll('a[href*="/in/"]')) {
    const href = a.href.split('?')[0];
    if (!/linkedin\.com\/in\/[^/]+/.test(href) || seen.has(href)) continue;
    let card = a.closest('li, [role="listitem"], article, .entity-result, .artdeco-list__item');
    if (!card) { card = a; for (let i = 0; i < 4 && card.parentElement && card.parentElement.tagName !== 'BODY'; i++) card = card.parentElement; }
    const text = (card.innerText || '').trim();
    if (!text) continue;
    seen.add(href);
    out.push({href, text});
  }
  return out;
}
"""

_NOISE = re.compile(
    r"^(connect|message|follow|following|pending|view .*profile|status is .*|.*mutual connection.*|.*followers?|.*follows? you|"
    r"send .*|more|•|\.{3}|see all|show more.*|\d+[km]?)$", re.I)
_DEGREE = re.compile(r"\b(1st|2nd|3rd)\b\+?", re.I)
_DEGREE_NUMBER = {"1st": 1, "2nd": 2, "3rd": 3}


def parse_card(href: str, text: str) -> dict | None:
    """A person from one result card's text: name, degree, headline, location. None when no name can be read."""
    lines = [l.strip() for l in text.replace("\r", "").split("\n") if l.strip()]
    degree = None
    cleaned: list[str] = []
    for line in lines:
        found = _DEGREE.search(line)
        if found and degree is None:
            degree = _DEGREE_NUMBER[found.group(1).lower()]
        line = re.sub(r"[•·]\s*(1st|2nd|3rd)\+?|\b(1st|2nd|3rd)\+?\s*degree connection", "", line, flags=re.I).strip(" •·")
        if not line or _NOISE.match(line) or _DEGREE.fullmatch(line):
            continue
        if cleaned and line == cleaned[-1]:
            continue
        cleaned.append(line)
    if not cleaned:
        return None
    name = re.sub(r"\s*(,?\s*(PhD|MBA|CPA|PMP))*$", "", cleaned[0]).strip()
    if not name or name.lower().startswith("linkedin member"):
        return None
    return {"profile_url": href, "name": name, "headline": cleaned[1] if len(cleaned) > 1 else "",
            "company": "", "location": cleaned[2] if len(cleaned) > 2 else "", "degree": degree}


async def read_people(page: Page) -> list[dict]:
    people = []
    for item in await page.evaluate(CARD_JS):
        person = parse_card(item["href"], item["text"])
        if person:
            people.append(person)
    return people


Progress = Callable[[list[dict]], Awaitable[None]]
ShouldStop = Callable[[], Awaitable[bool]]


async def _pause(low: float = 6.0, high: float = 14.0) -> None:
    await asyncio.sleep(random.uniform(low, high))


async def _wait_for_people(page: Page, timeout_ms: int = 25_000) -> None:
    try:
        await page.wait_for_selector('a[href*="/in/"]', timeout=timeout_ms)
    except Exception:  # noqa: BLE001 - an empty page is a normal end
        pass


def _with_page(url: str, number: int) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query["page"] = str(number)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


async def collect_search(page: Page, url: str, limit: int, max_pages: int, progress: Progress, should_stop: ShouldStop,
                         pause=_pause) -> list[dict]:
    """People from a LinkedIn people-search results URL, one page of results at a time."""
    found: dict[str, dict] = {}
    for number in range(1, max_pages + 1):
        if await should_stop():
            break
        await page.goto(_with_page(url, number), wait_until="domcontentloaded", timeout=45_000)
        await _wait_for_people(page)
        await page.mouse.wheel(0, 4000)  # results below the fold are rendered lazily
        await asyncio.sleep(1.5)
        fresh = [p for p in await read_people(page) if normalize_linkedin_url(p["profile_url"]) not in found]
        if not fresh:
            break
        for person in fresh:
            found[normalize_linkedin_url(person["profile_url"])] = person
        await progress(fresh)
        if len(found) >= limit:
            break
        await pause()
    return list(found.values())[:limit]


_REACTION_WORDS = {"like": "like", "celebrate": "celebrate", "support": "support", "love": "love", "insightful": "insightful",
                   "funny": "funny"}


async def collect_post(page: Page, post_url: str, reactions: list[str] | None, comments: bool, limit: int,
                       progress: Progress, should_stop: ShouldStop, pause=_pause) -> list[dict]:
    """People who reacted to (the chosen reaction types) and/or commented on one post."""
    found: dict[str, dict] = {}
    await page.goto(post_url, wait_until="domcontentloaded", timeout=45_000)
    await asyncio.sleep(4)
    if reactions is None or reactions:
        opener = page.locator("button.social-details-social-counts__count-value, button[aria-label*='reaction' i], "
                              ".social-details-social-counts__reactions button").first
        if await opener.count():
            await opener.click()
            await asyncio.sleep(2)
            dialog = page.locator("div[role='dialog']").first
            wanted = {_REACTION_WORDS[r] for r in (reactions or []) if r in _REACTION_WORDS}
            if wanted:
                for tab in await dialog.locator("button[role='tab'], button[aria-label]").all():
                    label = ((await tab.get_attribute("aria-label")) or (await tab.inner_text()) or "").lower()
                    if any(word in label for word in wanted):
                        await tab.click()
                        await asyncio.sleep(1.5)
                        await _scroll_collect(page, dialog, found, limit, progress, should_stop)
            else:
                await _scroll_collect(page, dialog, found, limit, progress, should_stop)
            await page.keyboard.press("Escape")
    if comments and len(found) < limit and not await should_stop():
        await _scroll_collect(page, page.locator("section.comments-comments-list, .comments-comments-list").first, found, limit,
                              progress, should_stop)
    return list(found.values())[:limit]


async def _scroll_collect(page: Page, scope, found: dict, limit: int, progress: Progress, should_stop: ShouldStop,
                          rounds: int = 12) -> None:
    for _ in range(rounds):
        if await should_stop() or len(found) >= limit:
            return
        fresh = [p for p in await read_people(page) if normalize_linkedin_url(p["profile_url"]) not in found]
        for person in fresh:
            found[normalize_linkedin_url(person["profile_url"])] = person
        if fresh:
            await progress(fresh)
        else:
            return
        try:
            await scope.evaluate("el => el.scrollBy(0, el.clientHeight || 800)")
        except Exception:  # noqa: BLE001 - the scope may not scroll; the page does
            await page.mouse.wheel(0, 1200)
        await asyncio.sleep(random.uniform(2.0, 4.0))


LINKEDIN_BASE = "https://www.linkedin.com"


async def collect_connections(page: Page, filters: dict, limit: int, progress: Progress, should_stop: ShouldStop,
                              base: str = LINKEDIN_BASE) -> list[dict]:
    """The sender's own 1st-degree connections, filtered by title, company, location and connected-since on our side."""
    await page.goto(f"{base}/mynetwork/invite-connect/connections/", wait_until="domcontentloaded", timeout=45_000)
    await _wait_for_people(page)
    found: dict[str, dict] = {}
    word = lambda key: (filters.get(key) or "").strip().lower()  # noqa: E731
    for _ in range(25):
        if await should_stop() or len(found) >= limit:
            break
        fresh = []
        for person in await read_people(page):
            key = normalize_linkedin_url(person["profile_url"])
            person["degree"] = 1
            blob = f"{person['headline']} {person['location']}".lower()
            if key in found or (word("title") and word("title") not in blob) or (word("company") and word("company") not in blob) \
                    or (word("location") and word("location") not in blob):
                continue
            found[key] = person
            fresh.append(person)
        if fresh:
            await progress(fresh)
        before = len(await page.evaluate(CARD_JS))
        await page.mouse.wheel(0, 3000)
        await asyncio.sleep(random.uniform(2.0, 4.0))
        if len(await page.evaluate(CARD_JS)) == before:
            break
    return list(found.values())[:limit]


async def collect_invitations(page: Page, limit: int, progress: Progress, should_stop: ShouldStop, base: str = LINKEDIN_BASE) -> list[dict]:
    """People who have invited the sender and are waiting for an answer. UNVERIFIED on the real site: the address and the card
    layout are the best known guesses until a run on a real account (with the owner's GO) shows the page."""
    await page.goto(f"{base}/mynetwork/invitation-manager/received/", wait_until="domcontentloaded", timeout=45_000)
    await _wait_for_people(page)
    found: dict[str, dict] = {}
    for _ in range(10):
        if await should_stop() or len(found) >= limit:
            break
        fresh = []
        for person in await read_people(page):
            key = normalize_linkedin_url(person["profile_url"])
            if key not in found:
                person["degree"] = None
                found[key] = person
                fresh.append(person)
        if fresh:
            await progress(fresh)
        before = len(await page.evaluate(CARD_JS))
        await page.mouse.wheel(0, 3000)
        await asyncio.sleep(random.uniform(2.0, 4.0))
        if len(await page.evaluate(CARD_JS)) == before:
            break
    return list(found.values())[:limit]
