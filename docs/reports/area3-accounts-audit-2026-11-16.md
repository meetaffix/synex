# Area 3: LinkedIn accounts, audit (16 Nov 2026)

Status words: **Works** (seen working), **Partial**, **Missing**. Evidence is a file and function, or what was seen on screen on
`http://localhost:5174/linkedin-accounts` with Meet Affix connected on this PC. Nothing here was tested on a hosted server.

## A. Accounts page

| Item | Status | Evidence |
|---|---|---|
| Cards with photo, name, headline, status, usage, limit | Partial | `AccountRow.tsx`. Photo and headline render but Meet Affix has **no headline or photo**: the selectors in `pages.py:85-86` return nothing on the real page (database row: headline and avatar null). Limit wording fixed today ("Stopped" / "N today, up to M a day") |
| Today's usage per action | Missing | One combined `dailyActionsUsed`; per-type counts exist only for invites and messages (`connections_today`, `messages_today`) |
| Last sync time, network status (online/offline, last seen) | Partial | `lastCheckedAt` only, no online/offline or last seen |
| Health warning | Partial | `problemHints` in `AccountRow.tsx` for three statuses |
| Statuses: connecting, connected, needs code, needs verification, session expired, reconnect needed, paused, restricted, error, archived | Partial | `accountStatusSchema` has only connected, needs_reconnect, restricted, paused, disconnected. Connecting/needs code/verification exist only inside the connect attempt, not on the account; error and archived do not exist |
| Seats used (1 of 3), plan placeholder | Missing | nothing in the page |
| Search and filter by status | Missing | `AccountsPage.tsx` has none |
| Empty state with Connect action | Works | `AccountsPage.tsx` `EmptyState`, `ConnectAccountEmpty` |

## B. Connect flow

| Item | Status | Evidence |
|---|---|---|
| Side panel with email/phone, password, sync preferences, optional proxy | Partial | It is a centred dialog (`ConnectDialog.tsx`), fields present (`CredentialsStep.tsx`) |
| No time zone field | Missing | `CredentialsStep.tsx:128` still shows "Time zone" |
| Progress with elapsed time | Works | `WaitingStep`, `StartingStep` (commit c13020a) |
| Survives a page refresh | Missing | attempt id kept only in React state (`useConnectFlow`) |
| Code step: Verify | Works | `CodeStep.tsx` |
| Resend code, Try another way | Missing | no such code in `manager.py` or the frontend |
| App approval waiting and timeout | Works | `WaitingStep` in `ConnectFlow.tsx`, 90 s pending limit |
| Checkpoint or puzzle with live view | Missing | `ManualStep.tsx` tells the person to use a normal browser |
| Wrong password, locked, timeout messages and retry | Works | `FailedStep.tsx`, `copy.ts`, tests in `test_linkedin_session.py` |
| Success screen: Done and Connect Another | Partial | `SucceededStep.tsx` has Done only |
| Duplicate protection | Works | `store.save_session`: same normalized profile URL updates the row |
| Connect-by-link | Partial | reconnect links exist (`routers/reconnect.py`, expiry and failure cap); they only reconnect an existing account and cannot create one |

## C. Account detail and settings

| Item | Status | Evidence |
|---|---|---|
| Profile summary (photo, name, headline, link, connections count) | Missing | no detail view; card only, no link, no count |
| Per-action daily limits with ranges and ceilings | Partial | one account limit in `EditAccountDialog.tsx`; per-type **ceilings** exist in `config.DAILY_TYPE_CEILINGS` (now 7 types) but are not editable per account |
| Ramp-up presets with preview | Missing | warm-up is fixed (`engine.effective_daily_limit`: 5 a day, +5) |
| Working hours per weekday and time zone | Missing | only on campaigns |
| Inbox sync preferences | Partial | mode (all / Synex only) in `SyncModeFields.tsx`; no "how far back" |
| Check now, pause/resume, reconnect, remove | Works | `AccountRow.tsx` menu; remove is "Disconnect" |
| Remove with confirmation explaining what is kept | Partial | `ConfirmDialog` exists; wording to be checked |
| Archive keeping history | Missing | no archived state |
| Per-account activity log | Missing | `agent_activity` rows are written (`outreach_results._audit`) but no API or screen |

## D. Session and health

| Item | Status | Evidence |
|---|---|---|
| Saved encrypted session reused without password | Works | seen 16 Nov: Check now reached the feed from the saved session |
| Health check before each work session | Missing | `_batch` in `outreach_worker.py` opens the browser and runs tasks; a logged-out page is detected on the first action (`_guard`), not by a check first |
| Detect logout/restriction, pause the account's campaigns, notify | Partial | `outreach_results.handle_session_error` sets the account status and requeues the task; campaigns are not paused and nobody is notified |
| Check now once per click | Fixed today | server drops a second check while one runs or within 30 s (`service.run_check`); button already shows loading |
| Network gate: no LinkedIn task from a hosted server IP | Missing | only the proxy gate `REQUIRE_ACCOUNT_PROXY` exists; the owner's rule is "no proxies", so this needs a different design (for example a `HOME_NETWORK_ONLY` flag that refuses to start browsers unless the worker is flagged as running on the owner's network) |

## E. Quality

Loading, empty and error states exist on the accounts page. Dark theme, 360 px and keyboard checks for this area have **not** been
re-done after today's changes. Full suites not yet run on `local-complete`.

## Found in the OutFlo notes (`roadmap-outflo` branch) and not on the list

- Per-action limits with a random daily range per account (11 actions at OutFlo), ceiling in code, plus a rule that no action ships without a ceiling (done today: `test_ceilings_cover_every_type.py`).
- Proxy mode and country shown on every account, and a warning when an account uses none (the owner's rule is no proxies, so this stays optional).
- Seats used per account and the plan, which belong with billing.
- Reconnect-link flow that can create an account for a named workspace (agency).
