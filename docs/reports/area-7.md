# Area 7: Dashboard and analytics (report)

Date: 2026-11-16. Branch `local-complete`. Local only; nothing pushed or deployed. Checklist 7.01 to 7.11 (11 lines: 7 done, 4 partial).

| Item | Status before | What I did | Test | Result |
|---|---|---|---|---|
| Headline numbers, trend chart, accounts table, attention panel, date range, campaign and account filters | Works (real rows) | Unchanged | existing dashboard states and app-shell tests | pass |
| Funnel: in campaigns, contacted, accepted, replied, interested, each with its share of the step before | Missing | New feed and panel; counted from real rows; honours every filter | test_dashboard_funnel (6); dashboard-funnel.spec (3) | pass |
| Results per campaign (leads, contacted, accepted, replied, interested, accepted %, reply %) | Partial (only in the campaigns list) | New feed and table; "No data" instead of a made-up 0% | same | pass |
| Interested uses the inbox labels | Missing | "Interested" and "Meeting booked" labels count | test_dashboard_funnel | pass |
| Export CSV (campaigns, time series, accounts) | Missing | Three exports with the same filters; spreadsheet formulas neutralised | same | pass |
| Numbers reconcile with the database | Missing | Test that seeds rows and checks every stage, the campaign table and that the daily export sums to the invitations sent | test_dashboard_funnel | pass |
| Per-account "limits used" on the dashboard | Missing | Not added: it is on the account list (area 3) | none | open (partial) |
| Chart reviewed against the data-viz rules, 768 px and screenshots | Missing | Not done | none | open |

Verification: backend test_dashboard_funnel 6 pass; Playwright dashboard-funnel 3 pass; axe and 360 px pass for all five dashboard states in both themes.

Standing reminders
- Secret scan broken in CI (deferred by the owner on 15 Nov 2026; must be fixed and run on full history before any public repo or real user).
- Clerk secret and CockroachDB password were exposed in chat on 15 Nov 2026 (rotation deferred; mandatory before any real user, pilot, production deploy or public repo).
