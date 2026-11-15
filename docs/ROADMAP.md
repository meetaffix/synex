# Synex roadmap

The single tracker for the project. Statuses: **Done**, **In progress**, **Next**, **Later**. Updated at the end of
every phase. Last update: 15 Nov 2026, 17:45.

## Done

| Item | Evidence |
|---|---|
| LinkedIn session connection | `backend/app/linkedin_session`; `test_linkedin_session.py` |
| Sender accounts UI | `frontend/src/features/linkedin-accounts`; `sender-accounts.spec.ts` |
| Phone login, sync preference, proxy test | same area |
| App shell | `frontend/src/components/shell` |
| Action executor and campaign engine | `engine.py`, `planner.py`, `outreach_worker.py`; `test_outreach.py` |
| Fix rounds 4F and carry-overs | commit `473a099` |
| Limits and hard ceilings | `config.py`; 0 means stopped; migration `007_limit_ceilings`; backend suite 224 tests OK |
| Design system and personality pass | `docs/DESIGN.md` |
| AI assistant on Deepgram | commit `adf36fb`; `docs/ASSISTANT.md`; 38 backend and 24 Playwright tests |
| Cleanup | commit `0d4bad2` |
| Extension removal | commit `0d4bad2` |
| Deepgram as the only AI service (drafting, post editing; spintax template fallback) | `deepgram_text.py`, `providers.py`; `test_drafting.py` (14 tests); Anthropic settings removed |
| Clerk authentication, off by default | `clerk_auth.py`, `routers/clerk.py`, `docs/CLERK_MIGRATION.md`; `test_clerk.py` (21 tests); sign-in rendered in a real browser; real sign-in not yet tried |
| Repository, CI and deploy configuration | Private repo `meetaffix/synex`; pull requests #1 and #2 merged; CI jobs: backend tests, frontend typecheck, build and browser tests, dependency audit green; secret scan non-blocking (see Known debt). `frontend/vercel.json`, `docs/DEPLOY.md`; no Vercel project yet |
| No AI calls while sending; drafts prepared before launch | `engine.message_for`, `app/drafts.py`; `test_prepared_messages.py` (19 tests); sequential suite 300 tests OK |
| One root `.env` with startup validation and bundle secret check | `app/check_env.py`, `frontend/scripts/check-bundle.mjs`, `docs/ENVIRONMENT.md`; `test_env.py` (22 tests) |
| Parallel test runner | `backend/run_tests.py`; three strict runs: 300 tests each, 0 failed, 241/244/245 s (sequential 448 s) |

## In progress

| Item | State |
|---|---|
| Design stage C: review screenshots in both themes (viewed after the final change), 1280 consistency pass, design report | Not started; the wording and hero size are committed |
| Database move to CockroachDB | Docs read; owner approval of the env audit and plan pending (see `docs/handover/`) |

## Next, in order

1. **Env file audit approval, then the database.** Rename and remove env variables as approved; CockroachDB support with retries, Alembic baseline, a data-migration script (dry run first), and the suite on both databases.
2. **Migration rehearsal on a copy of `synex.db`**, then go live locally on current code (the running API is still the 14 Nov code).
3. **Switch Clerk on** after the owner rotates the secrets and confirms the dashboard settings.
4. **Real LinkedIn test** with the owner's own account at very low limits, fixing selectors on the live site.
5. **Inbox:** read, reply, tags, interest labels, search; assistant tools for replies.

## Later

6. **Campaign builder:** visual branching flow (profile visit, like, follow, message, follow-up if no reply, stop on
   reply), editing live campaigns, launch celebration; assistant tools for designing flows.
7. **Lead import:** own connections, LinkedIn and Sales Navigator search URLs, people who reacted to a post (choose
   reaction types), import review.
8. **Safety extras:** do-not-contact lists, withdrawing old invitations, ramp-up presets, variable daily limits,
   sender archive.
9. **Reports:** per-campaign time series, step conversion, A/B tests, PDF export; campaign sparklines.
10. **Agency:** client workspaces, several senders per campaign with capacity rules, campaign duplication.
11. **Integrations:** webhooks, API keys, Slack, HubSpot.
12. **Deploy for pilot:** Postgres, containers, Oracle Cloud and Vercel runbook.
13. **Billing:** plans per LinkedIn account, trial, rupees and UPI.

## Known debt

- **Secret scan broken in CI, deferred by the owner on 15 Nov 2026.** Must be fixed and run against full history before
  any public repo, any production deploy, or any real user. State: the job runs (`continue-on-error: true`) so its
  result stays visible and it blocks no pull request; its 10 findings on 15 Nov are `generic-api-key` hits on
  placeholder values in `.github/workflows/ci.yml` and five test files (none real). The fix is an allowlist of those
  placeholders in `.gitleaks.toml`, then a clean run over the whole history.
- **Clerk secret and CockroachDB password were exposed in chat on 15 Nov 2026; rotation deferred by the owner.** Must
  be rotated before any real user, pilot or production deploy.
- **Rule for hosting:** Vercel gets only `VITE_API_URL` and `VITE_CLERK_PUBLISHABLE_KEY`. No server secret, no
  `DATABASE_URL`, no `CLERK_SECRET_KEY` and no `DEEPGRAM_API_KEY` goes into Vercel or any frontend variable (the
  bundle secret check fails the build if one does). Server secrets live only in the root `.env` on the backend host.

- Publishing pages use the legacy stylesheet block in `frontend/src/index.css`.
- Unused columns from the extension and the old login stay in the database (`agent_token`, `agent_last_seen_at`,
  `execution_mode`, `harvest_session_requested`, `cookie_harvested_at`, `li_at_encrypted`, `jsessionid_encrypted`,
  `cloud_status`); removing them is a separate migration decision. `settings.algorithm` is unused and goes with the Clerk phase.
- **Database columns nothing in the code reads or writes** (kept for a later migration, which is a separate decision;
  checked 15 Nov 2026 by searching every file for each name): `linkedin_accounts.sync_requested`,
  `linkedin_accounts.jsessionid_encrypted`, `linkedin_accounts.harvest_session_requested`,
  `sequence_runs.current_step_order` (only migration `006` reads it, to move old runs to step ids).
  Also still present because the old account serializer reads them: `agent_token`, `agent_last_seen_at`,
  `execution_mode`, `cookie_harvested_at`, `li_at_encrypted`, `cloud_status`. They go with the old login code when
  Clerk is switched on.
- Campaign connection and message limits exist in the API only; no screen edits them.
- The API on port 8010 runs code from before the limit fixes until it is restarted; back up `synex.db` first.
- Two Playwright specs expected the old button wording; they pass again once the wording commit is verified.
