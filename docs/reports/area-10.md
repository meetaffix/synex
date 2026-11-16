# Area 10: Settings and integrations (report)

Date: 2026-11-16. Branch `local-complete`. Local only. Checklist 10.01 to 10.25 (25 lines: 10 done, 11 partial, 4 open).

| Item | Status before | What I did | Test | Result |
|---|---|---|---|---|
| Notifications: emails, five toggles, test email, outbox | Missing | Settings stored per workspace; emails always saved in an outbox and sent through SMTP when `SMTP_HOST` is set | test_integrations (2); integrations.spec | pass (SMTP not exercised) |
| Events: reply received, account disconnected, campaign launched, interested label | Missing | Emitted to webhooks and notification emails | test_integrations | pass; account connected and campaign paused are not emitted yet |
| Webhooks and Slack: signed delivery (X-Synex-Signature), delivery log, test button, enable or disable, private addresses refused | Missing | Built; Slack accepts only hooks.slack.com | test_integrations WebhookTest (4); integrations.spec | pass |
| API keys and public API (campaigns, leads, conversations, create lead) | Missing | Keys shown once and stored hashed; revoke; last-used time | test_integrations KeyAndApiTest | pass |
| MCP server | Missing | JSON-RPC over HTTP at `/mcp` with the same key: Synex's read and draft tools; tools that change data are not offered | test_integrations | pass |
| Exports for Smartlead and Instantly | Missing | CSVs in each tool's column names, only people with an email | test_integrations; integrations.spec | pass |
| Importer for another tool's export | Missing | Leads and lists from a CSV; columns matched by name | test_integrations | partial (no campaigns or conversations) |
| HubSpot import | Missing | Token stored encrypted; imports contacts with a LinkedIn address | test_integrations (stand-in) | built, unverified on a real HubSpot account |
| Usage meter | Missing | Seats, leads, campaigns, AI messages and assistant minutes this month, actions in 24 hours; says plainly it is not a balance | test_integrations; integrations.spec | pass |
| Support form | Missing | Saved in the workspace | integrations.spec | partial (no email delivery) |
| Profile settings (name, phone, role, company) | Missing | Not built | none | open |
| Social post planner reviewers and manual engagement | Missing | Not built; the existing publishing module is unchanged | none | open |
| What's new panel | Missing | Not built | none | open |

New environment variable names: `ALLOW_PRIVATE_WEBHOOKS`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`. New tables: `api_keys`, `webhooks`, `webhook_deliveries`, `workspace_settings`, `outbox_emails`, `support_messages`.

Standing reminders
- Secret scan broken in CI (deferred by the owner on 15 Nov 2026; must be fixed and run on full history before any public repo or real user).
- Clerk secret and CockroachDB password were exposed in chat on 15 Nov 2026 (rotation deferred; mandatory before any real user, pilot, production deploy or public repo).
