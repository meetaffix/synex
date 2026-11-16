"""Open LinkedIn with a SAVED session (no password) and report whether it reaches the logged-in feed. One health check.

    cd backend
    python tools/session_reuse_check.py --workspace-email owner@example.com

Read-only: it reads the saved, encrypted session of the workspace's account(s) from the hosted database, decrypts it in memory,
runs the same health check the app's "Check" button runs, and prints the verdict. It writes NOTHING to the database. Run it twice
in two separate processes to show the session survives a restart: nothing is kept in memory between runs.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "tools"))

import login_probe  # noqa: E402  (reuses the hosted-database setup and the browser preflight)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace-email", required=True)
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    login_probe.preflight(headless=not args.headed)
    login_probe.point_at_hosted_database()

    from app import models
    from app.database import SessionLocal
    from app.linkedin_session import store
    from app.linkedin_session.manager import CheckFailed, SessionManager
    from app.linkedin_session.pages import LINKEDIN

    workspace = login_probe.find_workspace(args.workspace_email)
    if not workspace:
        print("no Synex user with that email in the hosted database")
        return 2
    with SessionLocal() as db:
        accounts = [a for a in db.query(models.LinkedInAccount).filter(models.LinkedInAccount.user_id == workspace)
                    if a.session_state_encrypted and a.browser_profile]
        loaded = [(a.id, store.load_state(a), a.browser_profile, store.load_proxy(a), a.daily_action_limit) for a in accounts]
    print(f"accounts with a saved session in this workspace: {len(loaded)}")
    manager = SessionManager(LINKEDIN, max_browsers=1, attempt_timeout=120, poll_interval=1.0, headless=not args.headed)
    code = 0
    try:
        for number, (_, state, identity, proxy, limit) in enumerate(loaded, 1):
            started = time.monotonic()
            try:
                result = manager.check_session(storage_state=state, identity=identity, proxy_url=proxy)
                verdict = result.status
            except CheckFailed as exc:
                verdict = f"check could not finish: {exc}"
                code = 1
            took = time.monotonic() - started
            print(f"  account {number}: health check -> {verdict} in {took:.1f}s (proxy: {'yes' if proxy else 'no'}, daily limit {limit}, "
                  f"timezone {identity.get('timezoneId')}); nothing written to the database")
            if verdict != "connected":
                code = code or 1
    finally:
        manager.shutdown()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
