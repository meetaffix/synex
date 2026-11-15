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
| CI, Vercel and deploy configuration (written, not pushed) | `.github/workflows/`, `frontend/vercel.json`, `docs/DEPLOY.md` |

## In progress

| Item | State |
|---|---|
| Design stage C: review screenshots in both themes (viewed after the final change), 1280 consistency pass, design report | Not started; the wording and hero size are committed |
| First push and CI | Waiting for write access to the private repository `meetaffix/synex` (see `docs/DEPLOY.md`) |
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

- Publishing pages use the legacy stylesheet block in `frontend/src/index.css`.
- Unused columns from the extension and the old login stay in the database (`agent_token`, `agent_last_seen_at`,
  `execution_mode`, `harvest_session_requested`, `cookie_harvested_at`, `li_at_encrypted`, `jsessionid_encrypted`,
  `cloud_status`); removing them is a separate migration decision. `settings.algorithm` and
  `access_token_expire_minutes` go with the Clerk phase.
- Campaign connection and message limits exist in the API only; no screen edits them.
- **Owner action:** the key in `backend/.env` must be named `DEEPGRAM_API_KEY` (it is `DEEPGRAM_APY_KEP` today).
- The API on port 8010 runs code from before the limit fixes until it is restarted; back up `synex.db` first.
- Two Playwright specs expected the old button wording; they pass again once the wording commit is verified.
