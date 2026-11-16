"""Run ONE LinkedIn login exactly as Synex does, from this machine, and record what happened. Login only.

    cd backend
    python tools/login_probe.py --identifier you@example.com                  # this PC, home connection, no proxy
    python tools/login_probe.py --identifier you@example.com --proxy http://user:pass@host:port   # through a proxy
    python tools/login_probe.py --identifier you@example.com --save-workspace-email owner@example.com   # also save the session

Use an expendable account. YOU type the password (hidden) and, if LinkedIn asks, the code. Nothing is sent, visited or liked:
the only pages opened are LinkedIn's sign-in page and your own profile page (to confirm the sign-in). Without
--save-workspace-email nothing is saved anywhere. With it, a successful login saves the ENCRYPTED session as a sender account in
that person's Synex workspace (the hosted database) with its daily limit set to 0 (stopped); nothing is saved if the login
fails. The result line (no secrets) is appended to backend/captures/probe-results.jsonl and printed; a redacted screenshot of
any failure is saved in backend/captures/ (this machine only, git-ignored).
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import httpx  # noqa: E402

CAPTURES = BACKEND / "captures"
HOSTED_DATABASE_HOST = "elated-mastiff-36818.j77.aws-ap-south-1.cockroachlabs.cloud:26257"


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


def point_at_hosted_database() -> None:
    """Build DATABASE_URL for the hosted CockroachDB from the root .env, in memory. Nothing is printed."""
    env = {}
    for line in (BACKEND.parent / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    user, password, database = (env[k] for k in ("COCKROACH_SQL_USER", "COCKROACH_SQL_PASSWORD", "COCKROACH_DATABASE"))
    # The public CA certificate shipped in the repo, not the AppData copy named in .env: that copy exists only for some shells.
    cert = str(BACKEND / "certs" / "cockroach-ca.crt")
    os.environ["DATABASE_URL"] = (f"cockroachdb://{quote(user, safe='')}:{quote(password, safe='')}@{HOSTED_DATABASE_HOST}/{database}"
                                  f"?sslmode=verify-full&sslrootcert={quote(cert, safe='')}")


def find_workspace(email: str) -> str | None:
    from app import models
    from app.database import SessionLocal
    with SessionLocal() as db:
        user = db.query(models.User).filter(models.User.email == email.strip().lower()).first()
        return user.id if user else None


def ip_facts(proxy: str | None) -> dict:
    """Country and network name of the address LinkedIn will see (never the address itself)."""
    try:
        kwargs = {"proxy": proxy} if proxy else {}
        data = httpx.get("https://ipinfo.io/json", timeout=15, **kwargs).json()
        return {"country": data.get("country"), "network": data.get("org")}
    except Exception as exc:  # noqa: BLE001
        return {"country": None, "network": f"lookup failed ({type(exc).__name__})"}


def probe_manager_class(save: bool):
    from app import models
    from app.database import SessionLocal
    from app.linkedin_session.manager import SessionManager

    class ProbeManager(SessionManager):
        """The same login code. A success is saved (encrypted, limit 0) only when asked; otherwise nothing is kept."""

        async def _conclude(self, attempt, signed_in, identifier, proxy_url):
            if not save:
                attempt.account_id = "not-saved"
                self._set_state(attempt, "succeeded")
                return
            await super()._conclude(attempt, signed_in, identifier, proxy_url)
            with SessionLocal() as db:  # the new account starts STOPPED, whatever the model's default is
                account = db.get(models.LinkedInAccount, attempt.account_id)
                account.daily_action_limit = 0
                db.commit()

    return ProbeManager


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--identifier", required=True, help="the LinkedIn email or phone")
    ap.add_argument("--proxy", help="optional: http://user:pass@host:port")
    ap.add_argument("--timezone", default="Asia/Kolkata")
    ap.add_argument("--label", default="", help="a name for this run, e.g. home-pc / hosted-noproxy / hosted-proxy")
    ap.add_argument("--headed", action="store_true", help="show the browser window")
    ap.add_argument("--timeout", type=int, default=240, help="seconds before giving up")
    ap.add_argument("--save-workspace-email", help="on success, save the session as a stopped sender account in this person's hosted workspace")
    args = ap.parse_args()
    preflight(headless=not args.headed)

    workspace_id = "probe"
    if args.save_workspace_email:
        point_at_hosted_database()
        workspace_id = find_workspace(args.save_workspace_email)
        if not workspace_id:
            print("workspace check FAILED: no Synex user with that email in the hosted database. Nothing was asked or sent.")
            return 2
        print("workspace check: ok (the session will be saved there, stopped, only if the login succeeds)")
        if input("This will WRITE to the hosted database if the login succeeds. Type YES to allow it, anything else to stop: ").strip() != "YES":
            print("Stopped. Nothing was asked, nothing was sent, nothing was written.")
            return 2

    from app.linkedin_session.identity import parse_proxy, validate_proxy_url, validate_timezone
    from app.linkedin_session.pages import LINKEDIN
    proxy = validate_proxy_url(args.proxy) if args.proxy else None
    if proxy:
        parse_proxy(proxy)
    timezone = validate_timezone(args.timezone)
    password = getpass.getpass("LinkedIn password (hidden, typed by you): ")

    facts = ip_facts(proxy)
    print(f"address seen by LinkedIn: country={facts['country']} network={facts['network']}")
    manager = probe_manager_class(bool(args.save_workspace_email))(
        LINKEDIN, max_browsers=1, attempt_timeout=args.timeout, poll_interval=1.0, headless=not args.headed, capture_dir=CAPTURES)
    started = time.monotonic()
    attempt = manager.start_login(workspace_id=workspace_id, identifier=args.identifier, password=password, proxy_url=proxy,
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
        "timezone": timezone, "saved": bool(args.save_workspace_email) and attempt.state == "succeeded",
        "account_limit_set_to_zero": bool(args.save_workspace_email) and attempt.state == "succeeded",
    }
    CAPTURES.mkdir(parents=True, exist_ok=True)
    with open(CAPTURES / "probe-results.jsonl", "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")
    print("\nRESULT " + json.dumps(row, indent=2))
    return 0 if attempt.state == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
