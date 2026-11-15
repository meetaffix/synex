# Environment variables

**One `.env` for the whole project**, in the project root next to `backend/` and `frontend/`. The API, both workers
and the Vite frontend read it. `.env.example` (same folder) lists every variable, with the optional ones commented out
at their defaults. `.env` is never committed; the old per-folder files (`backend/.env`, `frontend/.env`) are ignored.

How each part reads it:

| Part | How |
|---|---|
| Backend and workers | `app/config.py` (`ENV_FILE` is the root `.env`). Real environment variables set by the host override the file. |
| Frontend | `frontend/vite.config.ts` sets `envDir` to the root. Vite hands only names that start with `VITE_` to the browser; everything else in the file stays on the server. |

## Checking it

```bash
cd backend
python -m app.check_env
```

It prints one line per finding, with the variable **name** and what is wrong, and exits 1 if anything is an error. It
never prints a value. It reports: missing or short secrets, a bad `DATABASE_URL`, bad CORS origins, Clerk keys that are
missing or malformed when `AUTH_PROVIDER=clerk`, a Deepgram key of the wrong shape, old names that were renamed, names
that are no longer read, names no code reads (typos), old per-folder env files, and a database connection budget that
is exceeded.

The same check runs when the API, the outreach worker or the publishing worker starts. An error stops the process with
the names that are wrong (never the values).

## The built frontend must hold no secret

```bash
cd frontend
npm run build
npm run check:bundle
```

`check:bundle` scans every file in `dist/`. It fails if any value in the root `.env` whose name is not `VITE_*` and
looks secret (`KEY`, `SECRET`, `PASSWORD`, `TOKEN`, `DATABASE_URL`) appears there, or if a secret-shaped string does:
a Clerk secret key, a webhook signing secret, a private key block, or a database URL with a password. It prints the
variable name and the file, never the value. CI runs it after the build.

## Variables

| Variable | Needed | Notes |
|---|---|---|
| `SECRET_KEY`, `ENCRYPTION_KEY` | always | Independent random values, 32+ characters each. A new `ENCRYPTION_KEY` cannot read data encrypted with the old one. |
| `DATABASE_URL` | always | `sqlite:///./synex.db` locally; the CockroachDB URL when hosted (see `docs/DATABASE.md`) |
| `CORS_ORIGINS`, `CORS_ORIGIN_REGEX` | always / optional | Allowed origins; the regex must match a whole origin and be specific to this project |
| `AUTH_PROVIDER` | always | `local` or `clerk` |
| `CLERK_SECRET_KEY`, `VITE_CLERK_PUBLISHABLE_KEY` | with Clerk | The publishable key serves the backend and the frontend (one value, one name). `CLERK_WEBHOOK_SECRET` is optional. |
| `DEEPGRAM_API_KEY` | optional | Empty turns the assistant and AI drafting off; template drafts with variables and spintax are used |
| `VITE_API_URL` | frontend | Origin of the API |
| `FRONTEND_URL`, `COOKIE_SECURE` | when deployed | Links and the cookie flag |
| `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`, `LINKEDIN_REDIRECT_URI` | publishing | Secondary feature |
| `SMTP_*` | built-in sign-in only | **Unused when `AUTH_PROVIDER=clerk`** |
| `OUTREACH_*`, `LINKEDIN_SESSION_*`, `ASSISTANT_*` | optional | Tuning; defaults are in `.env.example` |

## Names that changed

| Old name | Now |
|---|---|
| `DEEPGRAM_APY_KEP` | `DEEPGRAM_API_KEY` |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_PUBLISHABLE_KEY` | `VITE_CLERK_PUBLISHABLE_KEY` |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | removed: Deepgram is the only AI provider |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | removed: Clerk replaces the old token lifetime |

## Hosting

The values are set in the host's environment settings, not by uploading the file. Where each one lives (Vercel,
GitHub, the backend host) is in `docs/DEPLOY.md`.
