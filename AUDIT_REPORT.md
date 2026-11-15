# SYNEX audit — 4 November 2026

## Baseline and preservation
The supplied directory is a ZIP extraction, not a Git checkout. No prior diff or commit history is available. React 19 / Vite / TypeScript / Tailwind frontend; FastAPI / SQLAlchemy backend; SQLite database; browser extension. Existing database and environment files must not be overwritten. There is no test suite or deployment orchestration in the supplied source.

## Findings before major changes
| Category | Evidence / root cause | Remediation |
|---|---|---|
| Critical integration | accounts.py pairs an extension; cloud_executor.py and extension/voyager.js use private Voyager endpoints. No official OAuth implementation. | Disable these execution surfaces; implement OAuth/OIDC and official Posts API. |
| False connection state | accounts._create accepts profile fields and sets active; update accepts status. | Only validated OAuth credentials establish a connection. |
| Sensitive data | Cloud mode harvests li_at and JSESSIONID; disconnect fails to clear cloud credentials. | Remove cookie ingestion and execution; clear deprecated credentials during migration. |
| Missing product workflow | Models contain leads, campaigns, conversations and tasks, but no publishing drafts, posts or publishing executions. | Add durable content and execution records without deleting old business records. |
| Scheduling reliability | In-process outreach and cloud loops lack durable publishing claims / ambiguous-result protection. | Separate restartable worker, atomic claims, bounded rate-limit retries, manual review after uncertain delivery. |
| Authentication | Empty secret permitted; seven-day browser-local JWT, no revocation; reset links logged. Team invitations can activate based on unverified email. | Enforce secret configuration, revoke sessions, stop secret logging and unsafe invitation activation. |
| Fake settings | 2FA and integrations are stored booleans with no actual authentication/provider setup. | Remove unsupported controls and reject activation. |
| Visual clutter | Purple gradients, glass utilities, animated marketing components, oversized cards, fabricated testimonial and metrics on auth screen. | Neutral surfaces, blue actions, compact dark navigation, typography and rows. |
| Navigation | Outreach-first shell omits studio/calendar; social login buttons only show a toast. | Publishing-first shell; remove nonfunctional sign-in controls. |
| Analytics | Existing metrics derive from outreach records, not authorized LinkedIn publishing analytics. | Explicit internal publishing metrics; no impressions/follower claims. |
| Partial capabilities | Imports, enrichment, messages, connections and campaign execution depend on extension/private APIs. | Preserve historical records and manual CRM; disable unsupported execution. |
| UX / accessibility | Error handling often replaces server errors with generic messages; dark default; decorative animations; keyboard-inaccessible password toggle. | Consistent errors/loading/empty states, accessible dialogs, responsive layout and reduced motion. |
| Performance | Synchronous provider calls; full-workspace scans in analytics; unused marketing code shipped through landing route. | Bounded worker operations, indexed publishing queries, remove marketing route and imports. |
| Migration | create_all plus unversioned ALTER statements; no migration history/rollback verification. | Add explicit versioned additive publishing migration and test repeat application against an existing database copy. |

## Route inventory and intended treatment
- Auth: retain email login/register/reset; repair sessions and error messages. LinkedIn connection remains separate from platform login.
- Dashboard, accounts, analytics, settings: replace unsafe/misleading workflows with publishing data.
- Studio, calendar, automation, activity: add missing real publishing workflows.
- Leads/lists/templates: retain useful local data management; remove scraping/enrichment execution.
- Campaigns/inbox: preserve historical records; replace unattended execution with clearly labeled manual workflows/history.
- Team: preserve records; do not auto-activate unverified email invitations.
- Extension help and marketing: retire production routes and decorative demos. Extension must no longer collect cookies or call LinkedIn.

## Implementation checklist
- [x] Secure platform sessions and retire private API execution
- [x] OAuth state, nonce, ID token, userinfo, scopes, expiry, encrypted tokens
- [x] Durable content, scheduling, locking, attempts and diagnostics
- [x] Redesign all production routes and preserve manual CRM
- [x] Mocked provider, ownership, retry and migration tests
- [x] Build and desktop/tablet/mobile interaction checks
- [x] Setup, integration, design, implementation and verification reports

Live LinkedIn publishing requires operator credentials and product access, plus explicit approval for live external writes. It is not part of automated local verification.

## Scope correction and outcome
The browser extension was retained as requested: it now captures ideas and launches the official workflows without cookie access. LinkedIn sign-in, explicit sign-in linking from Settings, and publishing consent are separate operations. The reports describe test coverage and remaining external gates; checked implementation steps do not imply live LinkedIn verification.
