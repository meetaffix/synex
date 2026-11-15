# SYNEX publishing workspace

React / TypeScript frontend, FastAPI / SQLAlchemy backend, official LinkedIn OAuth, a durable publishing worker, and an outreach worker.

## What works locally

- Email sign-in, registration, revocable HttpOnly sessions, profile preferences, password changes.
- Separate **Sign in with LinkedIn** and **Connect LinkedIn for publishing** flows.
- Text and single-image drafts, LinkedIn preview, approval, publish-now queue, scheduling with IANA time zones, pause, cancel, reschedule, execution history.
- Atomic worker claims, bounded retries for rate-limit responses, manual review after ambiguous delivery.
- Real internal analytics; manual contacts, CSV import/export, lists, templates, and preserved outreach history.

Live LinkedIn authorization and publishing have **not** been verified. The local installation now has a dedicated encryption key. It still needs a LinkedIn client ID and client secret. Video/document uploads, organization publishing, provider analytics, new team enrollment, and 2FA are not implemented. No unsupported scraping, bulk messaging, or private LinkedIn API execution is enabled.

## Local setup (Windows PowerShell)

Use Python 3.12 and a current Node LTS. Run commands from the indicated directory.

1. Back up `backend/synex.db` before applying migrations. Existing business records are preserved; deprecated pairing tokens and LinkedIn session cookies are intentionally cleared. Previously active outreach campaigns are paused. **Stop old SYNEX API/worker processes before upgrading**, so an old process cannot continue executing retired outreach code.
2. Copy `.env.example` to `.env` in the project root (one file for the backend, workers and frontend; see `docs/ENVIRONMENT.md`). Keep existing configuration that is still needed. Generate independent secrets with `python -c "import secrets; print(secrets.token_urlsafe(48))"` and set both `SECRET_KEY` and `ENCRYPTION_KEY`. Do not rotate the encryption key without reauthorizing all LinkedIn connections or a controlled re-encryption migration.
3. Install and run the API from `backend`. Use `verify_upgrade.py --apply` for an existing local database: it first checks two migrations on a copy, preserves business data in `backend/backups/` (keep those copies outside the project, they hold real data), then applies the verified migration. For a fresh database, use `python -m app.migrations` instead:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python verify_upgrade.py --apply
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

4. Run the worker in a separate terminal, also from `backend`:

```powershell
.\.venv\Scripts\python -m app.publishing_worker
```

The worker must remain running for scheduled/publish-now jobs to execute. The browser does not need to stay open. Pending jobs persist through restarts. A job interrupted during dispatch requires manual review, rather than an automatic resend.

5. Run the frontend from `frontend`:

```powershell
npm ci
npm run dev
```

Open [the local workspace](http://localhost:5173). The default API is `http://localhost:8010`. To change it, set `VITE_API_URL` in the root `.env` and restart Vite. Use the **same hostname** for API and frontend (`localhost` for both); do not mix `localhost` and `127.0.0.1` with SameSite cookies.

6. Open Settings → Connection diagnostics to inspect OAuth configuration, worker heartbeat, and AI configuration. Credentials are never displayed.

## LinkedIn account sessions (outreach)

Outreach accounts connect through a server-side Chromium session driven by Playwright, separate from the official OAuth flow below. The user enters their LinkedIn email and password once; the password is used for that login only and is never stored or logged. On success the browser's storage state is saved encrypted with `ENCRYPTION_KEY`, together with the profile name, headline, URL and avatar.

One-time setup, from `backend` (the new dependency is pinned in `requirements.txt`):

```powershell
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m playwright install chromium
```

Optional environment variables (defaults are in `backend/app/config.py`): `LINKEDIN_SESSION_MAX_BROWSERS` (concurrent browsers, default 3), `LINKEDIN_SESSION_ATTEMPT_TIMEOUT_SECONDS` (default 600), `LINKEDIN_SESSION_POLL_INTERVAL_SECONDS` (default 1.0) and `LINKEDIN_SESSION_HEADLESS` (default true).

Each account keeps a browser identity (user agent, viewport, locale, timezone) fixed at first connect and an optional proxy URL stored encrypted. Verification codes are entered through the API; app approvals are polled; any checkpoint SYNEX does not recognise (CAPTCHA, unknown security check) stops in `awaiting_manual_verification` and must be completed by the user on LinkedIn directly. SYNEX never solves or bypasses these.

The API is `/linkedin-accounts/...` (authenticated) and `/reconnect/...` (public, single-use 24-hour links, rate limited); see `backend/app/routers/accounts.py` and `reconnect.py`. All LinkedIn URLs and selectors live in `backend/app/linkedin_session/pages.py` and are **unverified against the live site**. Upgrading adds columns to `linkedin_accounts` (migration `004_browser_sessions`, additive only); back up `backend/synex.db` first, as described above.

**Reconnect links.** A link from *Send a link so the owner reconnects it* works once and expires after 24 hours. Issuing a new link for the same account replaces the old one. After 5 failed sign-in attempts through a link, the link stops working and a new one must be created. The public `/reconnect/...` routes are also rate limited per client, and a link only reconnects the account it was issued for.

## Outreach worker (running campaigns)

Campaigns execute through each account's saved browser session. Run the worker from `backend`, in its own terminal, next to the API:

```powershell
.\.venv\Scripts\python -m app.outreach_worker
```

Each cycle the worker queues due actions (`engine.tick`), claims them atomically, and performs them (connection requests, messages, profile visits, follows, acceptance checks, inbox reads) in the account's browser: one browser per account at a time, tasks strictly in order, a random gap between actions, a short batch per browser session, and refreshed cookies saved after every batch. The global browser cap is `LINKEDIN_SESSION_MAX_BROWSERS`. `Ctrl+C` stops claiming new work, lets the current action finish, and closes every browser.

**No double sends.** Every task has an idempotency key (run id + step id) with a unique index. A claim is a versioned update, and the lead's state is re-read just before acting. If a worker dies mid-action the task becomes `needs_review` and is never retried automatically; check LinkedIn, then use *retry* or *skip* on the run. Only tasks that failed before touching the page retry (backoff, at most `OUTREACH_TASK_MAX_ATTEMPTS`).

**Limits and ceilings.** A limit of 0 stops that action; it never means "no limit". Hard ceilings per account, in `backend/app/config.py` as constants that no setting, campaign or API call can raise: 40 connection requests a day and 150 a week, 100 messages, 80 profile visits and 50 follows a day, 200 actions a day in all. They count every campaign on the account. A value above a ceiling is refused with a 422 that names it. Migration `007_limit_ceilings` keeps stored 0s and lowers anything above a ceiling, logging each change.

**Safety.** A logged-out, checkpoint or restricted session stops that account (`needs_reconnect` or `restricted`, with `pausedReason` on the account) and Synex never solves or bypasses a checkpoint. With *pause on failure* set, a campaign pauses after `OUTREACH_MAX_CONSECUTIVE_FAILURES` failed tasks in a row. `OUTREACH_KILL_SWITCH=true`, or `POST /outreach/kill-switch {"enabled": true}` as a platform admin (`role` = Admin), stops all task execution immediately; `GET /outreach/status` shows it. `POST /campaigns/{id}/dry-run` lists the next 50 planned actions without sending anything.

Launching a campaign requires a connected sender account, a non-empty lead list, at least one step and valid working hours; each missing item is a separate 422. Daily counters roll over in the account's timezone, working hours use the campaign timezone (or the lead's own `timezone`), and each account has a weekly connection-request cap.

Settings (all optional; the defaults are in `backend/app/config.py`):

| Variable | Default | Meaning |
|---|---|---|
| `OUTREACH_KILL_SWITCH` | `false` | Stop all task execution |
| `OUTREACH_TICK_INTERVAL_SECONDS` | `30` | Worker polling interval |
| `OUTREACH_ACTION_GAP_MIN_SECONDS` | `45` | Shortest random pause between actions on one account, on top of the engine's own pacing |
| `OUTREACH_ACTION_GAP_MAX_SECONDS` | `180` | Longest random pause between actions on one account |
| `OUTREACH_LEASE_SECONDS` | `300` | How long a worker holds an account's browser; renewed before every action, so only one browser runs per account |
| `OUTREACH_BATCH_MAX_ACTIONS` | `5` | Actions per browser session before it is closed |
| `OUTREACH_WEEKLY_CONNECTION_LIMIT` | `100` | Connection requests per account per rolling 7 days (never above the 150 ceiling) |
| `OUTREACH_MAX_CONSECUTIVE_FAILURES` | `5` | Failed tasks in a row before *pause on failure* pauses a campaign |
| `OUTREACH_TASK_MAX_ATTEMPTS` | `3` | Automatic tries for a task that failed before touching the page |
| `OUTREACH_TASK_RETRY_BACKOFF_SECONDS` | `120` | First retry delay (doubles each attempt) |
| `OUTREACH_STALE_TASK_SECONDS` | `600` | A task still running after this long belonged to a dead worker: `needs_review` |
| `OUTREACH_ACCEPTANCE_CHECK_INTERVAL_HOURS` | `12` | Spacing of acceptance checks for pending invitations (each counts against limits) |
| `OUTREACH_INBOX_SYNC_INTERVAL_MINUTES` | `15` | Spacing of inbox reads per account (reply detection) |
| `LINKEDIN_PROXY_TEST_URL` | `https://ipinfo.io/json` | Neutral endpoint used by the proxy test (never LinkedIn) |
| `LINKEDIN_PROXY_TEST_TIMEOUT_SECONDS` | `10` | Proxy test timeout |
| `LINKEDIN_PROXY_TEST_ALLOW_PRIVATE` | `false` | Allow testing proxies on private or loopback addresses |

Upgrading adds columns and migrations `005_sync_preferences` and `006_outreach_executor` (existing runs move from step order to step id); back up `backend/synex.db` first, and **stop any old API or worker process** before restarting. The real-site selectors in `backend/app/linkedin_session/pages.py` are unverified.

## LinkedIn setup

Create a developer app, enable **Sign In with LinkedIn using OpenID Connect** and **Share on LinkedIn**, and register `http://localhost:8010/linkedin/callback` exactly. Set the client ID and secret server-side, restart the API, and use the app’s LinkedIn controls. Authentication requests only `openid profile email`; publishing connection requests the configured scope set including `w_member_social`.

For an existing email account, sign in with email, then open Settings → LinkedIn sign-in → Link my LinkedIn sign-in. This explicitly links the LinkedIn subject to your authenticated account. Connecting a publishing profile does not create a sign-in identity. Matching email alone never takes over an existing account. New LinkedIn sign-ups require a verified email returned by LinkedIn. Disconnecting publishing removes its local token and pauses scheduled posts; it preserves LinkedIn sign-in identity. To revoke the app’s upstream grant as well, remove SYNEX from LinkedIn’s permitted services settings.

## Verification

From `backend`:

```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
.\.venv\Scripts\python -m pip install pip-audit
.\.venv\Scripts\python -m pip_audit --progress-spinner off
```

From `frontend`:

```powershell
npm run build
npm audit
npx playwright install chromium
```

For browser tests, use isolated fixtures (never deploy the test server):

```powershell
# Terminal 1, backend directory. Creates/replaces ONLY tests/browser-test.db.
.\.venv\Scripts\python -m tests.browser_server
# Terminal 2, frontend directory
$env:VITE_API_URL='http://127.0.0.1:8011'
npm run dev -- --host 127.0.0.1 --port 5174
# Terminal 3, frontend directory
npm test
```

Tests use an explicitly named fake LinkedIn account and a mocked provider response. They perform no live LinkedIn writes. Screenshots and traces go to `frontend/test-results`. Restart the fixture server for a clean browser database.

## Deployment contract

Serve the frontend build over HTTPS, run the API and publishing worker under a process supervisor, and point both processes to the same durable database. Use a persistent local disk for SQLite and one API/worker pair; PostgreSQL is the intended multi-instance path but was not exercised here. Run migrations once before starting multiple processes. Configure `FRONTEND_URL`, `CORS_ORIGINS`, `LINKEDIN_REDIRECT_URI`, and `COOKIE_SECURE=true` for the deployed origin. Serve API and frontend on the same site to preserve SameSite cookie behavior. The callback must be reachable on the registered exact URI.

Provide edge request/body limits and a shared authentication rate limiter for multiple API instances; the included limiter is per process. The service supervisor should restart workers after failure and alert on a heartbeat older than two minutes. Back up the database and encryption secret securely. Apply a frontend CSP and security headers at your static host. `/health` is liveness; administrator diagnostics separately expose worker status without infrastructure secrets. `npm run preview` and Vite development mode are not production servers.

Content library reads are currently limited to the latest 1,000 posts, activity to 200 events. Retention/pagination at larger scale, operator alert integrations, video/document upload, managed secret rotation, and real-environment load tests remain further work. This is not a claim of production certification.

## Folder layout

| Folder | Contents |
|---|---|
| `backend/` | FastAPI API, workers and tests. `synex.db` lives here and is never committed |
| `backend/app/` | Application code: routers, models, migrations, outreach engine and planner, publishing, `linkedin_session` browser sessions |
| `backend/tests/` | Backend unit tests plus the fixture server and mocks used by the browser tests |
| `frontend/` | React / Vite / TypeScript app and its Playwright browser tests (`frontend/tests`) |
| `frontend/src/` | Pages and features, shared components, services and the design tokens in `index.css` |
| `docs/` | `DESIGN.md` is the single design reference; `prompts/` holds the design prompt |
| `.env` (project root) | The one environment file for backend, workers and frontend; never committed. `.env.example` lists every variable, `docs/ENVIRONMENT.md` explains them |
| `.claude/` | Local Claude Code settings for this project |

## Design

See [docs/DESIGN.md](docs/DESIGN.md).
