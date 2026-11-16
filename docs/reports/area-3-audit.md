# Area 3 audit — 16 November 2026

Baseline: local branch `local-complete`, HEAD `80450f1`. Existing uncommitted edits in session actions/selectors, capture tooling and lead import UI predate this session and are preserved. No LinkedIn or hosted service was contacted. Source inspection is evidence of implementation, not a claim of live verification.

The owner confirmed `C:/Users/iamdn/Downloads/b8239b7a-attachment.txt` is the intended OutFlo inspection. It was copied unchanged to `docs/reference/outflo-inspection-2026-11-16.txt`. Its narration is historical reference, not execution instructions. Scope below covers the owner's area 3 requirements and reference sections 4, 2.3 and 6.2.

## Baseline checks

| Check | Result |
|---|---|
| Backend `python run_tests.py` | Finished: 354 tests in 405.6 seconds; 352 pass, 2 fail. AccountApiTest ignores the new check cooldown; NewAccountLimitTest expects only four ceiling types instead of seven. |
| Frontend `npm run typecheck` | Passed. |
| Frontend `npm run build` | Passed; existing large chunk and Zod annotation warnings. |
| Playwright `npm test` | First attempt blocked by project Vite on 5174. Verified and stopped that Vite only; rerun running, 256 tests discovered. |
| Bundle secret check | Passed; values not printed. |
| Theme contrast | All 100 token pairs pass. This is not a full screen accessibility review. |

## Accounts list and connection

| Item | Before | Evidence |
|---|---|---|
| List, profile avatar/name/headline, status | Partial | `frontend/src/features/linkedin-accounts/AccountRow.tsx:AccountRow`; nullable profile fields; no active-campaign count. |
| Organization overview, seats and plan placeholder | Partial | `AccountsPage.tsx:SenderAccountsPage` shows seats and Free placeholder; no overview card or available-seat count. |
| All / Active / Needs attention filter | Partial | `SenderAccountsPage` has search and individual status options; no aggregate Active/Needs attention. |
| Search and pagination | Partial | `SenderAccountsPage` filters client-side; no pagination. |
| Rolling 24-hour usage per action and ranges | Missing | `schemas.py:AccountOut.from_model` exposes one local-calendar-day total; no per-type ranges. |
| Accepted/reply performance chips | Missing | `AccountRow` has no performance chips. |
| Connect drawer | Partial | `ConnectDialog.tsx` uses centered Dialog; credential login exists. |
| Credentials and owner-entered verification codes | Works | `routers/accounts.py:connect,submit_code`; `ConnectFlow.tsx`, `CodeStep.tsx`; existing mock coverage. Live access requires GO. |
| Extension connection option (deferred extension implementation) | Missing | No extension choice in current connect UI; roadmap records extension removal. |
| Share connection link | Partial | `accounts.py:reconnect_link`, `ReconnectLinkDialog.tsx`; only existing accounts, not a new sender. |
| Empty/loading/error states | Works | `AccountsPage.tsx:EmptyState,LoadingList,Problem`. |
| Connection refresh recovery | Missing | `useConnectFlow` stores active attempt in component state. |

## Account detail and limits

| Item | Before | Evidence |
|---|---|---|
| Dedicated account page, profile header and connection metadata | Missing | `app/App.tsx` has list route only; `AccountRow` has last check, no detail route. |
| Resync and refresh | Partial | `accounts.py:check_account` validates session with cooldown; no profile/connections resync workflow. |
| SSI/percentile/confidence | Missing | No score provider or persisted source evidence; must never fabricate scores. |
| Sender Limits / Inbox Privacy / Health / Account / Manage Connections / AI Configuration tabs | Missing | Only `EditAccountDialog.tsx:EditAccountDialog`. |
| Recommended limits, Apply / Keep / Show suggestions | Missing | `EditAccountDialog` exposes a single total limit. |
| Conservative +1/week, balanced +2/2–3 days, aggressive +3/day | Missing | `engine.py:effective_daily_limit` uses fixed total warm-up of 5 +5/day. |
| Custom per-action increase / stop / interval | Missing | No account action-policy schema. |
| Range selector ±1 through ±10 | Missing | No range setting or deterministic bounded daily budget. |
| Profile views / invites / messages / follows / checks limits | Partial | `config.py:DAILY_TYPE_CEILINGS`, `engine.py:type_room,emit_task`; hard ceilings exist, account-specific settings absent. |
| Likes / active checks / withdraw / paid and free InMail limits | Missing | Not represented in `DAILY_TYPE_CEILINGS` or account UI. |
| Profile-related daily cap and variable activity | Partial | Overall cap 200, individual ceilings, pacing and total warm-up exist; no combined profile-related cap of 100. |
| Campaign sender selection and aggregate capacity | Partial | `CampaignBuilderPage.tsx` supports sender selection and launch gates; no allocation drawer. |
| Campaign action allocation and capacity priority | Missing | No per-campaign reservation settings or enforcement. |

## Privacy, health, lifecycle and connections

| Item | Before | Evidence |
|---|---|---|
| Full inbox / Synex-only privacy choice | Works | `SyncModeFields.tsx`; `service.py:require_sync_owner`, `store.py:can_change_sync_mode`. |
| Owner-only privacy warning and share link | Partial | `canChangeSyncMode` is enforced; existing reconnect link is not a privacy-sharing workflow. |
| Auto-withdraw stale invites and age threshold | Missing | No policy, scheduler or withdraw executor. |
| Deactivate seat and release capacity | Missing | Pause exists; no deactivated-seat lifecycle. |
| Delete account distinct from deactivation | Partial | `disconnect_account` wipes session and keeps record/history, not permanent account deletion. |
| Connection list and received invitation tabs | Missing | No account-scoped UI or received invitation sync. |
| Reload connections using paced tasks | Partial | `collect.py:collect_connections` exists for imports; no account management flow. |
| Export connections CSV | Missing | No account-scoped connections export. |
| Upload connections CSV, search and dedupe | Missing | Lead CSV features exist elsewhere, no account-scoped management. |
| Gradual sync notice and state | Missing | No connections screen. |
| Per-account activity log | Partial | `models.py:AgentActivity` persists worker activity; no account detail UI. |

## AI configuration and social engagement (reference 6.2)

| Item | Before | Evidence |
|---|---|---|
| Assigned voice and voice chooser | Missing | No sender voice assignment in account schemas/UI. |
| Preset samples and assignment | Missing | No commercially licensed voice catalog or playback. |
| Voice cloning, record/upload 30–60 sec, ownership confirmation | Missing | No cloning provider or licensed model integration. |
| Social board/calendar, Draft/In review/Scheduled/Published/Needs action | Partial | `features/publishing` and `publishing_models.py` implement publishing workflow; statuses and board parity incomplete. |
| Post editor, sender, 3000-char copy, mentions, media, first comment | Partial | `publishing/Studio.tsx`; current verified scope text/single image; video/document/mentions/first comment incomplete. |
| Team/external review, time reservation, feedback | Partial | Publishing approval exists; no external reviewer portal or feedback thread. |
| Duplicate/version history/delete draft | Partial | Draft lifecycle exists; version history incomplete. |
| Manual six reactions, comment drafts, identity and history | Missing | No engagement execution workflow. |
| External reviewer magic links and standalone portal | Missing | No reviewer link model/routes. |

## Verification limits and debt

No live LinkedIn verification is authorized yet. Missing implementations are **not** marked built. All real-site paths require the owner's GO before exercising them. The existing reports identify deferred CI secret-scan repairs and deferred Clerk/database credential rotation; neither was changed or verified in this session. No dependencies have been added.

