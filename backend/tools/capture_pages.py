"""Read-only capture of two real LinkedIn pages (the account's own profile and the messaging list) from the LOCAL database,
to fix selectors. One page load each. Nothing is clicked or typed. The output is a structure outline with all text replaced by its
length: tag, classes, role, attribute NAMES (never values, except the path of /in/ links). Written to --out (outside the repo).

    cd backend
    python tools/capture_pages.py --account "Meet Affix" --out ../../synex-backups/captures
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OUTLINE_JS = r"""
() => {
  const skip = new Set(['SCRIPT','STYLE','NOSCRIPT','svg','SVG','PATH','LINK','META','CODE']);
  function walk(el, depth) {
    if (skip.has(el.tagName) || depth > 14) return null;
    const attrs = [...el.attributes].map(a => a.name).filter(n => n !== 'class' && n !== 'style').sort();
    const node = {t: el.tagName.toLowerCase(), c: (el.getAttribute('class') || '').split(/\s+/).filter(Boolean).slice(0, 6), a: attrs.slice(0, 8)};
    const role = el.getAttribute('role'); if (role) node.role = role;
    const href = el.getAttribute('href'); if (href && /\/in\//.test(href)) node.href = '/in/…';
    const own = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join('').length;
    if (own) node.text = own;
    const kids = [];
    for (const k of el.children) { const w = walk(k, depth + 1); if (w) kids.push(w); }
    if (kids.length) node.k = kids.slice(0, 40);
    return node;
  }
  return {title: document.title.replace(/[^|]*\|/, '…|'), path: location.pathname.replace(/\/in\/[^/]+/, '/in/…'), body: walk(document.body, 0)};
}
"""


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", choices=["profile", "messaging"])
    ap.add_argument("--wait", type=int, default=6)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    from app import models
    from app.config import settings
    from app.database import SessionLocal
    from app.linkedin_session import store
    from app.linkedin_session.service import get_manager

    assert settings.database_url.startswith("sqlite"), "local database only"
    with SessionLocal() as db:
        account = db.query(models.LinkedInAccount).filter(models.LinkedInAccount.name == args.account).first()
        state, identity, url = store.load_state(account), account.browser_profile, account.linkedin_url
    manager = get_manager()

    async def work(page, context):
        for name, target in (("profile", url), ("messaging", "https://www.linkedin.com/messaging/")):
            if args.only and name != args.only:
                continue
            await page.goto(target, wait_until="domcontentloaded", timeout=45_000)
            await page.wait_for_timeout(args.wait * 1000)
            if name == "messaging":  # poll in this same load until the first row has content (up to 60 s)
                try:
                    await page.wait_for_function(
                        "() => { const li = document.querySelector('li.msg-conversation-listitem'); return li && li.querySelectorAll('*').length > 12; }",
                        timeout=60_000)
                    await page.wait_for_timeout(4_000)
                except Exception:  # noqa: BLE001
                    print("rows did not fill in 60 s")
            data = await page.evaluate(OUTLINE_JS)
            (out / f"{name}.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
            print(name, "path:", data["path"], "-> saved")
            await page.wait_for_timeout(3_000)

    await asyncio.wrap_future(manager.submit_session_work(storage_state=state, identity=identity, proxy_url=None, work=work))
    manager.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
