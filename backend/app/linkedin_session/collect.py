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
    // The card is a list item that holds this person (a mutual-connection link inside it is another person, but this link comes first),
    // else the largest ancestor that still holds links to this one person only. A fixed climb reaches a container shared by
    // several rows, and every row then gets the first person's name (seen on the real connections page, which has no list items).
    const people = (el) => new Set([...el.querySelectorAll('a[href*="/in/"]')].map((x) => x.href.split('?')[0]));
    let card = a.closest('li, [role="listitem"], article, .entity-result, .artdeco-list__item');
    if (card && people(card).size > 1 && card.querySelector('a[href*="/in/"]') !== a) card = null;
    if (!card) {
      card = a;
      for (let i = 0; i < 8 && card.parentElement && card.parentElement.tagName !== 'BODY' && people(card.parentElement).size <= 1; i++) card = card.parentElement;
    }
    const text = (card.innerText || '').trim();
    if (!text) continue;
    seen.add(href);
    out.push({href, text});
  }
  return out;
}
"""

_NOISE = re.compile(
    r"^(connect|message|follow|following|pending|view .*profile|status is .*|connected on .*|.*mutual connection.*|.*followers?|.*follows? you|"
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

# Seen on the real post page (25 Nov 2026): every reactor is a link to /in/<id> labelled
# "<Name> reacted with <Reaction>[, <degree>, <headline>]"; the viewer's own row says ", You,". The avatar row under the post is
# wrapped in a link to the post itself, and clicking it opens the full list in a native <dialog>. Nothing else is clicked: the
# Like button sits next to it and must never be touched.
REACTOR_JS = r"""
() => {
  const scope = document.querySelector('dialog[open]') || document.querySelector('[role="dialog"]') || document;
  const out = [];
  const seen = new Set();
  for (const a of scope.querySelectorAll('a[aria-label*=" reacted with "][href*="/in/"]')) {
    const href = a.href.split('?')[0];
    if (seen.has(href)) continue;
    seen.add(href);
    out.push({href, label: a.getAttribute('aria-label') || ''});
  }
  return out;
}
"""

OPEN_REACTORS_JS = r"""
() => {
  const first = document.querySelector('a[aria-label*=" reacted with "]');
  let el = first && first.parentElement;
  while (el && !(el.tagName === 'A' && /\/feed\/update\//.test(el.getAttribute('href') || ''))) el = el.parentElement;
  if (!el) return false;
  el.click();
  return true;
}
"""

# Comment cards. UNVERIFIED on the new real UI (the test post had no comments): the old class names plus any element whose
# component key or test id says comment. Each card's first /in/ link is the commenter.
COMMENT_JS = r"""
() => {
  const out = [];
  const seen = new Set();
  const cards = [...document.querySelectorAll('article.comments-comment-entity, article.comments-comment-item, ' +
    '[componentkey*="comment" i], [data-testid*="comment" i], [data-id*="comment" i]')];
  for (const card of cards) {
    // On the real page a "pagedCommentsContainer" wraps the whole post with its author: only the innermost boxes are comments,
    // and never one that holds the post's own reaction controls.
    if (cards.some((other) => other !== card && card.contains(other))) continue;
    if (card.querySelector('[aria-label^="Reaction button state"], a[aria-label*=" reacted with "]')) continue;
    if (/^\s*Feed post\b/.test(card.innerText || '')) continue;
    const a = card.querySelector('a[href*="/in/"]');
    if (!a) continue;
    const href = a.href.split('?')[0];
    if (seen.has(href)) continue;
    const text = (card.innerText || '').trim();
    if (!text) continue;
    seen.add(href);
    out.push({href, text});
  }
  return out;
}
"""

_DEGREE_PART = re.compile(r"^(1st|2nd|3rd)\+?( degree connection)?$", re.I)


def parse_reactor(href: str, label: str) -> dict | None:
    """A reactor from the link's label. None for the viewer's own row and for unreadable labels."""
    name, _, rest = label.partition(" reacted with ")
    parts = [p.strip() for p in rest.split(",")]
    if not name.strip() or not parts[0] or "You" in parts[1:2]:
        return None
    degree, headline = None, []
    for part in parts[1:]:
        found = _DEGREE_PART.match(part)
        if found and degree is None:
            degree = _DEGREE_NUMBER[found.group(1).lower()]
        elif part:
            headline.append(part)
    return {"profile_url": href, "name": name.strip(), "headline": ", ".join(headline), "company": "", "location": "",
            "degree": degree, "reaction": parts[0].lower()}


async def read_reactors(page: Page) -> list[dict]:
    return [p for p in (parse_reactor(i["href"], i["label"]) for i in await page.evaluate(REACTOR_JS)) if p]


async def read_commenters(page: Page) -> list[dict]:
    people = []
    for item in await page.evaluate(COMMENT_JS):
        person = parse_card(item["href"], item["text"])
        if person:
            person["location"] = ""  # the line after the headline is the comment itself
            people.append(person)
    return people


async def collect_post(page: Page, post_url: str, reactions: list[str] | None, comments: bool, limit: int,
                       progress: Progress, should_stop: ShouldStop, pause=_pause) -> list[dict]:
    """People who reacted to (the chosen reaction types) and/or commented on one post. Only the people on this post are read:
    the viewer's own profile card, the author and the "people you may know" panel are never taken as leads."""
    found: dict[str, dict] = {}
    await page.goto(post_url, wait_until="domcontentloaded", timeout=45_000)
    await asyncio.sleep(4)
    author = normalize_linkedin_url(await page.evaluate(
        """() => { const a = document.querySelector('main a[href*="/in/"]:not([aria-label*=" reacted with "])'); return a ? a.href : ''; }"""))
    if reactions is None or reactions:
        wanted = {_REACTION_WORDS[r.lower()] for r in (reactions or []) if r.lower() in _REACTION_WORDS}
        opened = await page.evaluate(OPEN_REACTORS_JS)
        if opened:
            try:
                await page.wait_for_selector("dialog[open], [role='dialog']", timeout=10_000)
            except Exception:  # noqa: BLE001 - the list did not open; the avatar row under the post is still read
                pass
            await asyncio.sleep(1.5)
        for _ in range(12):
            if await should_stop() or len(found) >= limit:
                break
            fresh = [p for p in await read_reactors(page)
                     if normalize_linkedin_url(p["profile_url"]) not in found and (not wanted or p["reaction"] in wanted)]
            for person in fresh:
                found[normalize_linkedin_url(person["profile_url"])] = person
            if fresh:
                await progress(fresh)
            before = len(await page.evaluate(REACTOR_JS))
            await page.evaluate("""() => { const d = document.querySelector('dialog[open], [role="dialog"]'); if (!d) return;
                for (const el of [d, ...d.querySelectorAll('*')]) if (el.scrollHeight > el.clientHeight + 4) el.scrollTop = el.scrollHeight; }""")
            await asyncio.sleep(random.uniform(2.0, 4.0))
            if not opened or len(await page.evaluate(REACTOR_JS)) == before:
                break
        if opened:
            dismiss = page.locator("dialog[open] button[aria-label='Dismiss'], [role='dialog'] button[aria-label='Dismiss']").first
            if await dismiss.count():
                await dismiss.click()
            else:
                await page.keyboard.press("Escape")
            await asyncio.sleep(1)
    if comments and len(found) < limit and not await should_stop():
        fresh = [p for p in await read_commenters(page)
                 if (key := normalize_linkedin_url(p["profile_url"])) not in found and key != author][: limit - len(found)]
        for person in fresh:
            found[normalize_linkedin_url(person["profile_url"])] = person
        if fresh:
            await progress(fresh)
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
    for _ in range(max(25, limit // 8)):  # every connection: keep scrolling until the list stops growing (LinkedIn allows 30,000)
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


# ---------------------------------------------------------------- more sources
# Everything below is UNVERIFIED on real LinkedIn: it reads pages by the same shape-based rules as above and is exercised only
# against the local mock pages. Sales Navigator, Recruiter and event pages need an account with access (or attendance).

SEAT_CARD_JS = r"""
() => {
  const out = [];
  const seen = new Set();
  for (const a of document.querySelectorAll('a[href*="/sales/lead/"], a[href*="/talent/profile/"]')) {
    const m = a.href.match(/\/(?:sales\/lead|talent\/profile)\/([^,/?#]+)/);
    if (!m || seen.has(m[1])) continue;
    let card = a.closest('li, [role="listitem"], article, tr') || a.parentElement;
    const text = (card.innerText || '').trim();
    if (!text) continue;
    seen.add(m[1]);
    out.push({id: m[1], text});
  }
  return out;
}
"""

COMPANY_CARD_JS = r"""
() => {
  const out = [];
  const seen = new Set();
  for (const a of document.querySelectorAll('a[href*="/company/"], a[href*="/sales/company/"]')) {
    const m = a.href.match(/\/(?:sales\/)?company\/([^/?#]+)/);
    if (!m || seen.has(m[1])) continue;
    let card = a.closest('li, [role="listitem"], article, tr') || a.parentElement;
    const text = (card.innerText || '').trim();
    if (!text) continue;
    seen.add(m[1]);
    out.push({id: m[1], text});
  }
  return out;
}
"""


async def read_seat_people(page: Page) -> list[dict]:
    """People on a Sales Navigator or Recruiter results page. The member id in the card link opens the public profile at /in/<id>."""
    people = []
    for item in await page.evaluate(SEAT_CARD_JS):
        person = parse_card(f"https://www.linkedin.com/in/{item['id']}", item["text"])
        if person:
            people.append(person)
    return people


async def read_companies(page: Page) -> list[dict]:
    """Companies on a company results page: name, the industry or place line, and the company page (a numeric id also opens it)."""
    companies = []
    for item in await page.evaluate(COMPANY_CARD_JS):
        lines = [l.strip() for l in item["text"].replace("\r", "").split("\n") if l.strip() and not _NOISE.match(l.strip())]
        if not lines:
            continue
        companies.append({"company_url": f"https://www.linkedin.com/company/{item['id']}/", "name": lines[0],
                          "headline": lines[1] if len(lines) > 1 else "", "location": lines[2] if len(lines) > 2 else "", "degree": None})
    return companies


async def collect_paged(page: Page, url: str, limit: int, max_pages: int, progress: Progress, should_stop: ShouldStop, reader,
                        wait_selector: str, pause=_pause) -> list[dict]:
    """Walk a results address page by page with ``reader``; used for Sales Navigator, Recruiter and company results."""
    found: dict[str, dict] = {}
    for number in range(1, max_pages + 1):
        if await should_stop():
            break
        await page.goto(_with_page(url, number), wait_until="domcontentloaded", timeout=45_000)
        try:
            await page.wait_for_selector(wait_selector, timeout=25_000)
        except Exception:  # noqa: BLE001 - an empty or blocked page is a normal end; the caller reports zero people
            pass
        await page.mouse.wheel(0, 4000)
        await asyncio.sleep(1.5)
        fresh = []
        for person in await reader(page):
            key = normalize_linkedin_url(person.get("profile_url")) or person.get("company_url", "").lower()
            if key and key not in found:
                found[key] = person
                fresh.append(person)
        if not fresh:
            break
        await progress(fresh)
        if len(found) >= limit:
            break
        await pause()
    return list(found.values())[:limit]


async def collect_event(page: Page, event_url: str, limit: int, progress: Progress, should_stop: ShouldStop) -> list[dict]:
    """People attending a LinkedIn event. The sender must be marked as attending, or LinkedIn shows no attendee list."""
    found: dict[str, dict] = {}
    await page.goto(event_url, wait_until="domcontentloaded", timeout=45_000)
    await asyncio.sleep(3)
    opener = page.locator("a:has-text('attendees'), button:has-text('attendees'), a:has-text('Attendees'), button:has-text('Attendees')").first
    scope = page.locator("body")
    if await opener.count():
        await opener.click()
        await asyncio.sleep(2)
        dialog = page.locator("div[role='dialog']").first
        if await dialog.count():
            scope = dialog
    await _scroll_collect(page, scope, found, limit, progress, should_stop)
    return list(found.values())[:limit]


async def collect_own_post_engagers(page: Page, limit: int, progress: Progress, should_stop: ShouldStop, base: str = LINKEDIN_BASE,
                                    max_posts: int = 5) -> list[dict]:
    """People who reacted to or commented on the sender's own most recent posts. "All activity" also lists posts the sender only
    reacted to, so the posts-only page is read: /in/me/ redirects only on the all-activity page, which gives the real address first.
    Seen on 25 Nov 2026 with an account that has no posts yet; reading a real list of own posts is UNVERIFIED."""
    await page.goto(f"{base}/in/me/recent-activity/all/", wait_until="domcontentloaded", timeout=45_000)
    await asyncio.sleep(3)
    profile = re.match(r"(.*/in/[^/]+)/", page.url)
    if profile and "/in/me/" not in page.url:
        await page.goto(f"{profile.group(1)}/recent-activity/shares/", wait_until="domcontentloaded", timeout=45_000)
        await asyncio.sleep(4)
    hrefs = await page.evaluate("""() => [...new Set([...document.querySelectorAll('a[href*="/feed/update/"]')].map(a => a.href.split('?')[0]))]""")
    found: dict[str, dict] = {}
    for post in hrefs[:max_posts]:
        if await should_stop() or len(found) >= limit:
            break
        for person in await collect_post(page, post, None, True, limit - len(found), progress, should_stop):
            found.setdefault(normalize_linkedin_url(person["profile_url"]), person)
        await _pause(3.0, 7.0)
    return list(found.values())[:limit]
