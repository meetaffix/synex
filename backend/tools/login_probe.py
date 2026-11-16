"""Run ONE LinkedIn login exactly as Synex does, from this machine, and record what happened. Login only.

    cd backend
    python tools/login_probe.py --identifier you@example.com                  # run 1: this PC, home connection, no proxy
    python tools/login_probe.py --identifier you@example.com --proxy http://user:pass@host:port   # through a proxy

Use an expendable account. YOU type the password (hidden) and, if LinkedIn asks, the code. Nothing is sent, visited or liked:
the only pages opened are LinkedIn's sign-in page and your own profile page (to confirm the sign-in). Nothing is saved to any
database. The result line (no secrets) is appended to backend/captures/probe-results.jsonl and printed; a redacted
screenshot of any failure is saved in backend/captures/.
"""
from __future__ import annotations

import argparse
import getpass
import json
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import httpx  # noqa: E402

from app.linkedin_session.identity import parse_proxy, validate_proxy_url, validate_timezone  # noqa: E402
from app.linkedin_session.manager import SessionManager  # noqa: E402
from app.linkedin_session.pages import LINKEDIN  # noqa: E402

CAPTURES = BACKEND / "captures"


class ProbeManager(SessionManager):
    """The same login code, but a success is only reported: no session is saved anywhere."""

    async def _conclude(self, attempt, signed_in, identifier, proxy_url):
        attempt.account_id = "not-saved"
        self._set_state(attempt, "succeeded")


def preflight(headless: bool) -> None:
    """Start the browser against about:blank BEFORE anything is typed. If it cannot start, say why and stop."""
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            try:
                browser.new_page().goto("about:blank")
                print(f"browser check: ok (Chromium {browser.version}, {'headless' if headless else 'headed'})")
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001
        lines = str(exc).strip().splitlines()
        print("browser check FAILED. Nothing was asked, nothing was sent, LinkedIn was not contacted.")
        print("  " + (lines[0][:200] if lines else type(exc).__name__))
        print("  If the browser is not installed, run:  python -m playwright install chromium")
        raise SystemExit(2)


def ip_facts(proxy: str | None) -> dict:
    """Country and network name of the address LinkedIn will see (never the address itself)."""
    try:
        kwargs = {"proxy": proxy} if proxy else {}
        data = httpx.get("https://ipinfo.io/json", timeout=15, **kwargs).json()
        return {"country": data.get("country"), "network": data.get("org")}
    except Exception as exc:  # noqa: BLE001
        return {"country": None, "network": f"lookup failed ({type(exc).__name__})"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--identifier", required=True, help="the LinkedIn email or phone")
    ap.add_argument("--proxy", help="optional: http://user:pass@host:port")
    ap.add_argument("--timezone", default="Asia/Kolkata")
    ap.add_argument("--label", default="", help="a name for this run, e.g. home-pc / hosted-noproxy / hosted-proxy")
    ap.add_argument("--headed", action="store_true", help="show the browser window")
    ap.add_argument("--timeout", type=int, default=240, help="seconds before giving up")
    args = ap.parse_args()
    proxy = validate_proxy_url(args.proxy) if args.proxy else None
    if proxy:
        parse_proxy(proxy)
    timezone = validate_timezone(args.timezone)
    preflight(headless=not args.headed)
    password = getpass.getpass("LinkedIn password (hidden, typed by you): ")

    facts = ip_facts(proxy)
    print(f"address seen by LinkedIn: country={facts['country']} network={facts['network']}")
    manager = ProbeManager(LINKEDIN, max_browsers=1, attempt_timeout=args.timeout, poll_interval=1.0, headless=not args.headed,
                           capture_dir=CAPTURES)
    started = time.monotonic()
    attempt = manager.start_login(workspace_id="probe", identifier=args.identifier, password=password, proxy_url=proxy,
                                  timezone=timezone, identity=None, target_account_id=None)
    password = ""
    history: list[tuple[float, str]] = []
    page_states: list[str] = []
    try:
        while attempt.active:
            now = time.monotonic() - started
            if not history or history[-1][1] != attempt.state:
                history.append((round(now, 1), attempt.state))
                print(f"  {now:6.1f}s  state: {attempt.state}")
            if attempt.last_state and (not page_states or page_states[-1] != attempt.last_state):
                page_states.append(attempt.last_state)
                print(f"  {now:6.1f}s  page: {attempt.last_state}")
            if attempt.state == "awaiting_code":
                code = getpass.getpass("LinkedIn sent a code. Type it (hidden): ")
                manager.submit_code(attempt, code.strip())
            time.sleep(0.5)
    finally:
        seconds = round(time.monotonic() - started, 1)
        manager.shutdown()
    d = attempt.diagnosis
    row = {
        "label": args.label, "when": time.strftime("%Y-%m-%d %H:%M:%S"), "outcome": attempt.state, "seconds": seconds,
        "states": [s for _, s in history], "page_states": page_states,
        "failure_code": attempt.error[0] if attempt.error else None,
        "failure_message": attempt.error[1] if attempt.error else None,
        "classification": d.classification if d else None, "title": d.title if d else None,
        "path": d.path if d else None, "screenshot": d.screenshot if d else None,
        "proxy": bool(proxy), "country": facts["country"], "network": facts["network"], "headless": not args.headed,
        "timezone": timezone,
    }
    CAPTURES.mkdir(parents=True, exist_ok=True)
    with open(CAPTURES / "probe-results.jsonl", "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")
    print("\nRESULT " + json.dumps(row, indent=2))
    return 0 if attempt.state == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
