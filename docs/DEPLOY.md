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
