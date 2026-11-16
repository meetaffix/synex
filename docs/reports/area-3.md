# Area 3: LinkedIn accounts (report)

Date: 2026-11-16. Branch `local-complete`. Local only; nothing pushed or deployed.
Source: OutFlo report sections 4, 2.3, 6.2; checklist lines 3.A to 3.I in `docs/CHECKLIST.md`.

## Table

Status before = what existed when this build started (see `docs/reports/area-3-audit.md`). Result: pass = test passes, LV = not verified on real LinkedIn.

| Item | Status before | What I did | Test | Result |
|---|---|---|---|---|
| Accounts list: overview card (plan, seats used/available) | Partial (text "Seats used: n of 3") | Card from `/linkedin-accounts/overview`, billing marked placeholder | accounts-list.spec "overview card" | pass |
| Row: 24 h usage (connections, messages) with today's range | Missing | Added to overview payload and row | accounts-list.spec "24-hour usage"; test_account_overview | pass |
| Row: Smart pill | Missing | Shown when preset is not Fixed | same | pass |
| Row: accepted % and replied % | Missing | Computed from the leads of the account's campaigns; "no data" instead of 0% when nothing contacted | test_account_overview (3 tests); accounts-list.spec | pass |
| Status filter All / Active / Needs attention (+ single statuses) | Partial | Group options added | accounts-list.spec "filter" | pass |
| Name search, paging (9 per page) | Partial (search only) | Paging added | accounts-list.spec "paged" | pass |
| Empty state, loading, error | Works | Unchanged | sender-accounts.spec (existing) | pass |
| Connect dialog: credentials | Works (real LinkedIn verified 15 Nov) | Unchanged | sender-accounts.spec (existing) | pass |
| Connect via extension | Missing | Disabled button "Coming soon", reason shown | accounts-list.spec "connect dialog" | pass |
| Share connection link for a new sender | Missing | `POST /linkedin-accounts/invite-link` creates a stopped account (limit 0) and a one-time link | test_account_delete InviteLinkTest; accounts-list.spec | pass |
| Account page, header, tabs, Resync | Missing | New page with six tabs, URL keeps the tab, keyboard arrows | account-management.spec #1 | pass |
| Header banner: photo, profile link, connected since | Missing | Added | account-management.spec #1 | pass |
| SSI score | Missing | Honest "no data" text; never a made-up score (Synex has no verified SSI source) | account-management.spec #7 | pass |
| Sender limits: banner, 24 h table, presets, range, per-action table, ceilings | Partial (single number) | Full tab, ceilings enforced in UI and server | account-management.spec #2 to #5; test_account_policy (existing) | pass |
| Inbox privacy + owner-only lock + share with owner | Partial | Tab, lock note, share link dialog | account-management.spec #6 and "send the owner a link" | pass |
| Health: summary, recent activity, auto-withdraw setting | Missing | Summary and activity added. **Auto-withdraw execution is not built** (area 11); the page says so | account-management.spec #7 | pass (execution open) |
| Account: deactivate seat | Missing | Endpoint and confirm dialog | account-management.spec #8; test_account_delete | pass |
| Account: delete (permanent, typed name) | Missing | Endpoint and dialog; account leaves the list and seat count, session wiped, pending actions cancelled | test_account_delete (3 tests); account-management.spec "delete" | pass |
| Manage connections: list, search, paging, invitations | Missing | New table, endpoints, tab | test_account_connections (10); account-management.spec (4) | pass; LV |
| Reload, export CSV, upload CSV, gradual-sync notice | Missing | Paced reader with its own ceiling 12/day; CSV formula-safe export; upload with counts | same | pass; LV |
| AI configuration: assigned voice, preset voices with licences | Missing | Catalogue of 9 commercially licensed Piper voices, assignment endpoint | test_voices (3); account-management.spec "AI configuration" | pass |
| Voice samples | Missing | Disabled with reason: Piper engine not installed | account-management.spec "AI configuration" | built, engine not installed |
| Clone my voice | Missing | Disabled "Coming soon" with the reason; no model verified | same | not built on purpose (licence) |
| English (India) accent | Missing | Shown as unavailable with reason (no licensed voice exists) | same | n/a |
| Post likes, withdraw invite, InMail rows in the limits table | Missing | Not added: those action types do not exist yet. They arrive with areas 5 and 11 | none | open |
| Campaign action allocation | Missing | Part of area 5 (campaign builder step 1) | none | moved to area 5 |

## Verification

- Backend: full suite 384 tests, 0 failed (`run_tests.py -j 8`, 320 s). New tests this area: connections (10), overview (3), delete and invite link (7 incl. inherited), voices (3).
- Typecheck: clean. Production build: succeeds (a bundle-size warning exists, recorded for area 12).
- Playwright dev server: account-management 16, accounts-list 6, sender-accounts 24 pass. Axe and 360 px checks on 9 account states, both themes: pass.
- Full Playwright against `vite preview`: see the result line in the handover.
- Screens saved in `docs/reports/screens/area-3/` (both themes, 360, 768, 1280). I looked at the limits page at 360 dark and the connections tab at 1280 light. The selected-list button on the connections tab was too faint, so I made it stronger.
- Real LinkedIn: connection and invitation readers and the connect flow are the only parts that touch LinkedIn. The connect flow was verified on 15 Nov 2026. The readers are LV (selectors only fixture-tested); a real read needs your GO.

## Known gaps carried forward
1. Auto-withdraw of stale invitations: setting saved, nothing is withdrawn (area 11).
2. Extra action rows in the limits table (likes, withdraw, InMails) with areas 5 and 11.
3. Voice samples need Piper installed; cloning needs a licensed model (see `docs/DEPENDENCIES.md`).
4. Keyboard walk-through test of the account page is not yet a dedicated test (arrow keys between tabs are tested).

## Standing reminders
- Secret scan broken in CI (deferred by the owner on 15 Nov 2026; must be fixed and run on full history before any public repo or real user).
- Clerk secret and CockroachDB password were exposed in chat on 15 Nov 2026 (rotation deferred; mandatory before any real user, pilot, production deploy or public repo). A commented-out `.env` line still holds the CockroachDB password in plain text.
