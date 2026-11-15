# Deploying Synex: source control, CI and the frontend on Vercel

Status on 15 Nov 2026: the workflow files and `frontend/vercel.json` are written and committed locally. **Nothing
has been pushed.** The only GitHub repository named `synex` (`IAMDNMR/synex`) is **public** and empty, so the first
push waits for the owner (see "Owner to-do"). No Vercel project exists yet.

**The backend is not hosted yet.** A Vercel deployment serves only the frontend. Until the backend is deployed
(roadmap: "Deploy for pilot"), a Vercel preview or production site can be used to review the interface only: sign-in
and every data screen need the API.

## How CI works (`.github/workflows/ci.yml`)

Runs on every push and pull request. It needs **no real secret**: the tests use temporary databases and the local mocks
for LinkedIn, Deepgram and Clerk, and every value they need is set by the test itself.

| Job | What it does |
|---|---|
| Backend tests | Python 3.12, installs `backend/requirements*.txt` and Chromium, runs `python -m unittest discover -s tests` |
| Frontend typecheck, build and browser tests | Node 22, `npm ci`, `npm run typecheck`, `npm run build`, `npm run contrast`, then the Playwright specs in Chromium against the mock API (`--grep-invert "review screenshots"`) |
| Secret scan | gitleaks over the whole history (`fetch-depth: 0`), configured by `.gitleaks.toml` |
| Dependency audit | `npm audit --omit=dev --audit-level=high` and `pip-audit` (pip-audit has no severity filter, so any known vulnerability fails it) |

Failed browser runs upload `frontend/test-results` as an artifact for seven days.

## Previews and production

- **Preview deployments** come from Vercel's GitHub integration for every branch and pull request except `main`.
- **Production** is deliberately **not** automatic. `frontend/vercel.json` sets `git.deploymentEnabled.main` to
  `false`, so a push to `main` does not deploy. Production deploys run only through the manual workflow
  `.github/workflows/deploy-production.yml`:
  1. it must be started on `main` and the input `DEPLOY` typed;
  2. the `check` job requires a **successful CI run for that exact commit**;
  3. the `deploy` job uses the GitHub environment `production`, which the owner configures with a required reviewer,
     so a person approves before it starts;
  4. it runs `vercel pull`, `vercel build --prod` and `vercel deploy --prebuilt --prod`.
- `frontend/vercel.json` also sets the SPA rewrite (every path serves `index.html`) and the security headers:
  `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`, `Strict-Transport-Security`,
  `Permissions-Policy` (microphone allowed for the assistant only) and a `Content-Security-Policy-Report-Only`.
  The CSP is report-only on purpose: it allows Clerk and any `https:`/`wss:` API. Tighten `connect-src` to the real API
  origin and switch the header to `Content-Security-Policy` once the backend has a fixed address and the browser
  console shows no violations.

## Rolling back a Vercel deployment

In Vercel: Project, Deployments, open the last good production deployment, then "Promote to Production" (or "Instant
Rollback" from the current one). From the CLI: `vercel rollback <deployment-url>`. A rollback does not change the
environment variables; changing a `VITE_*` variable needs a new build.

## Where each setting lives (names only)

| Where | Names |
|---|---|
| Vercel project, Environment Variables (owner sets) | `VITE_API_URL` (the deployed API origin), `VITE_CLERK_PUBLISHABLE_KEY` |
| GitHub, Actions secrets (owner sets) | `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID` (only for the production workflow) |
| Backend host environment | `SECRET_KEY`, `ENCRYPTION_KEY`, `DATABASE_URL`, `CORS_ORIGINS`, `CORS_ORIGIN_REGEX`, `FRONTEND_URL`, `COOKIE_SECURE`, `AUTH_PROVIDER`, `CLERK_SECRET_KEY`, `CLERK_PUBLISHABLE_KEY`, `CLERK_WEBHOOK_SECRET`, `DEEPGRAM_API_KEY`, `LINKEDIN_*`, `SMTP_*` |
| Never in any of the above | the values themselves are never committed; CI uses only placeholders defined in the workflow |

### Origins the backend must allow

The backend takes its allowed origins from `CORS_ORIGINS` (a comma-separated list) and an optional
`CORS_ORIGIN_REGEX` that must match the **whole** origin. The same set is used for CORS, the origin check on writes
and Clerk's authorized parties (`azp`). Once the Vercel project exists:

- set `CORS_ORIGINS` to the production domain (and `http://localhost:5173` for local work);
- set `CORS_ORIGIN_REGEX` to this project's preview pattern, for example
  `https://synex(-[a-z0-9]+)*-meetaffix-1903s-projects\.vercel\.app`. Never use a `*.vercel.app` wildcard: it would
  admit every site hosted on Vercel.

## Branching

- Work happens on feature branches, one per roadmap item (for example `feature/inbox`, `feature/campaign-builder`).
- `main` receives changes only by pull request with CI passing. The branch protection settings are listed in the
  owner to-do because they live in GitHub's settings.

## Owner to-do

**GitHub**
1. Decide the repository. The existing `IAMDNMR/synex` is **public**. Either make it private (Settings, Danger zone,
   Change visibility) or create a new private repository, then tell me which. I will not push to a public repository.
2. After the first push, protect `main` (Settings, Branches, Add rule): require a pull request, require the status
   checks "Backend tests", "Frontend typecheck, build and browser tests", "Secret scan" and "Dependency audit", block
   force pushes and deletion, include administrators.
3. Create the environment `production` (Settings, Environments) with yourself as required reviewer.
4. Add the Actions secrets `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID` when the Vercel project exists.

**Vercel**
1. Approve the access request for the team that I sent, so the connection can see projects.
2. Import the GitHub repository as a project with root directory `frontend`; leave the build settings to
   `frontend/vercel.json`.
3. Set `VITE_API_URL` and `VITE_CLERK_PUBLISHABLE_KEY` for Preview and Production.

**Clerk**
1. Add each Vercel domain (production and the preview pattern's host) as an allowed origin of the Clerk application.
2. When the backend has an address, create the webhook to `/clerk/webhook` and keep its signing secret as
   `CLERK_WEBHOOK_SECRET` on the backend only.

---

# Railway: the plan for the backend (nothing exists on Railway yet)

Status 15 Nov 2026. **Nothing is created on Railway until the CockroachDB move is done and the owner approves this
plan in chat.** The Railway connector is signed in (workspace "Affix Official's Projects", 0 projects). Facts marked
**(docs)** were read from docs.railway.com on 15 Nov 2026; numbers marked **UNVERIFIED** are my estimates and must be
checked on Railway's pricing page before the plan is approved.

## 1. Services and why each exists

| Service | Runs | Why it exists |
|---|---|---|
| `synex-api` | `uvicorn app.main:app` (FastAPI) | Serves the frontend's API, the assistant's WebSocket relay and Clerk token checks. Always on. One replica. |
| `synex-outreach-worker` | `python -m app.outreach_worker` | The only process that drives LinkedIn in a real browser. It needs Chromium, so it has its own container (a Dockerfile from the Playwright Python image). Exactly one replica: the lease system already keeps one browser per account, and a second replica would only add cost. |

**Two services, not three.** The publishing worker (`python -m app.publishing_worker`) serves the secondary publishing
feature, which needs a LinkedIn OAuth app and is not part of the outreach pilot. It is not deployed. If publishing is
used later it becomes a third service (about the cost of the API: see the table), and that is a separate decision.

The database is CockroachDB (not a Railway service). The frontend is on Vercel.

## 2. Persistence: a redeploy or restart keeps every account connected

Nothing LinkedIn-related lives on a container's disk. Everything an account needs to stay connected is stored encrypted
in the database (`linkedin_accounts`: `session_state_encrypted` (cookies and storage), `browser_profile` (user agent,
viewport, locale, timezone), `proxy_url_encrypted`, status columns), using `ENCRYPTION_KEY`. A worker or API container
starts with an empty disk, reads the account from the database and opens a fresh browser with the stored state.

- **Volume: none needed. Size 0 GB, cost $0.** (If one is ever needed, Railway volumes cost $0.15 per GB-month (docs).)
- **Proof (test):** `test_worker_process.FreshDiskTest` starts a brand-new worker process with an empty temporary
  directory and no files from any earlier process, against a database that holds a connected account, and asserts the
  account is still `connected`, the worker acts with the stored session and the task is done. A redeploy is exactly
  that situation.
- `ENCRYPTION_KEY` must be the same value across deploys. A new key makes every stored session unreadable and every
  account must reconnect.

## 3. Cost control

**Browser cap.** `LINKEDIN_SESSION_MAX_BROWSERS` (default 3) limits concurrent Chromium instances in the worker. A hard
ceiling of 5 (`MAX_BROWSERS_CEILING` in `config.py`) cannot be exceeded by any setting, and `python -m app.check_env`
fails above it. **Recommended for the pilot: 2.** More accounts than browsers take turns (the lease system queues them),
so the number of accounts does not raise memory, only the time one pass takes.

**Billing model (docs).** A monthly subscription plus per-minute resource usage: vCPU, memory and network egress, and
volumes if any. The Hobby plan is $5 a month and includes $5 of usage; usage above that is charged. You are billed for
what runs, not for what is provisioned.

**Estimate (UNVERIFIED rates; accuracy about plus or minus 50%).** Assumes continuous running, the browser cap at 2, and
the rates I recall from Railway's pricing page: about $20 per vCPU-month, $10 per GB-month of memory, $0.05 per GB of
egress. Average use, not peak:

| Connected accounts | `synex-api` (avg) | `synex-outreach-worker` (avg) | Egress | Volume | Estimated monthly usage |
|---|---|---|---|---|---|
| 1 | 0.05 vCPU, 0.2 GB | 0.10 vCPU, 0.4 GB | about 1 GB | none | about $9 |
| 3 | 0.08 vCPU, 0.25 GB | 0.25 vCPU, 0.9 GB | about 3 GB | none | about $18 |
| 10 | 0.15 vCPU, 0.3 GB | 0.50 vCPU, 1.8 GB (cap 2 browsers) | about 10 GB | none | about $35 |

The invoice is the larger of $5 and the usage (the $5 subscription is covered by the included $5). Add the database
(CockroachDB Basic, billed by CockroachDB, not Railway) and Clerk and Deepgram usage (Deepgram: $0.075 per minute of
Voice Agent time; each AI draft is billed as about 10 seconds). Re-measure with Railway's service metrics after the
first week and replace these numbers with real ones.

**Hard spending limit: the owner sets it in the Railway dashboard BEFORE the first deploy.** Steps (docs: Pricing, Cost
Control, Usage limits):
1. Open Railway and switch to the workspace "Affix Official's Projects".
2. Open the workspace **Usage** page.
3. Click **Set Usage Limits**.
4. For **Compute Usage**, set a **Custom email alert** (for example $20) and a **Hard limit** (for example $40). Whole
   dollars only. The hard limit stops services when it is reached, so choose it above the expected bill for the number
   of accounts in use.
5. Save, then confirm the two values on the Usage page. (The same can be read or set with `railway usage` in the CLI.)

## 4. Datacenter IPs: connect accounts through a per-account proxy

A Railway server's IP address is a datacenter address, not a residential one, and LinkedIn treats those differently.
**Real LinkedIn accounts must connect and act through a per-account proxy in the owner's own region**, set per account
in Synex (the proxy field on the sender account; stored encrypted). The Phase 7 real-LinkedIn test **must use that proxy
and must never run straight from the Railway IP.** Until an account has a proxy, the worker should not be allowed to act
for it on Railway (a check to build before the first real account is connected).

## 5. Secrets

Railway variables hold the server secrets: `SECRET_KEY`, `ENCRYPTION_KEY`, `DATABASE_URL`, `CORS_ORIGINS`,
`CORS_ORIGIN_REGEX`, `AUTH_PROVIDER`, `CLERK_SECRET_KEY`, `VITE_CLERK_PUBLISHABLE_KEY` (the backend reads this one name
too), `CLERK_WEBHOOK_SECRET` (optional), `DEEPGRAM_API_KEY`, `LINKEDIN_SESSION_MAX_BROWSERS`. **The owner sets them in
the Railway dashboard. They are never set by Claude and never committed.** Vercel still receives only `VITE_API_URL` and
`VITE_CLERK_PUBLISHABLE_KEY`; the bundle secret check fails the build if a server secret reaches the frontend.

## 6. Deploys: only from `main`, only after CI passes

- Each service is connected to the repository `meetaffix/synex`, branch **`main`** only. Pull-request and branch
  environments are off. No deploy from a feature branch.
- Turn on **Wait for CI** (docs: Build & deploy, GitHub Autodeploys): Railway then waits for the GitHub Actions workflow
  to pass before deploying a commit. (The secret scan job is non-blocking by the owner's decision and does not hold a
  deploy; every other job must be green.)
- Pre-flight before the first deploy: the CockroachDB move is done and verified; the spending limit is set; the Railway
  variables are set by the owner; the worker Dockerfile and the per-account proxy rule are in `main`.

**Rollback.** Railway keeps previous deployments. In the service's **Deployments** list, click the three dots at the end
of the last good deployment and confirm **Rollback** (docs: Deployment Actions). A rollback restores the code and the
build, not the database: if a deploy included a migration, restore from the database backup or roll forward with a fix.
Variables are not rolled back. Roll back the worker and the API together so they stay on the same schema.
