# Verification report — 5 November 2026

Tests use a separate SQLite database, artificial member identities, local consent pages and simulated provider responses. Real workspace data was used only for migration verification and the preview smoke check.

| Check | Evidence |
| --- | --- |
| Backend | 23 tests passed using unittest. Coverage includes OAuth state and browser binding, signed token claims, sign-in versus publishing permissions, email collision handling, scope and expiry, session revocation, workspace isolation, draft persistence, and manual CRM. |
| Publishing | Worker tests cover single-claim concurrency, bounded rate-limit retries, ambiguous delivery, restart recovery, disconnect/pause, image validation, account ownership, and rejecting an untrusted upload destination. No test sent a LinkedIn post. |
| Extension | Chromium loaded the actual extension. The test saved an idea locally, transferred it to the studio through sign-in, opened account management, and checked unsafe workspace URL handling. |
| LinkedIn browser flows | Sign-in requested identity scopes only. Publishing requested a separate grant. The connected account remained after reload; disconnect required reconnecting for publishing while the sign-in identity remained linked. |
| Workspace controls | Created a contact, list and template, saved a time-zone preference and reloaded it, navigated the calendar, refreshed diagnostics, collapsed and expanded navigation, and confirmed sign-out protected the settings page. |
| Database upgrade | Ran the migration twice on a copy. Row counts and preserved-column hashes matched across 17 original tables; foreign-key check returned no violations. Applied the verified upgrade and checked the source data again. |
| Build and dependency checks | TypeScript/Vite production build passed. Publishing frontend formatting passed. npm audit and pip-audit found no known dependency vulnerabilities at the time of testing. The build emitted dependency annotation warnings. |
| Local preview | The login page returned HTTP 200, the API health check returned ok, and the worker recorded a heartbeat in the upgraded database. |

## Browser suite result

All four Chromium workflows passed in the final run. The publishing journey saved and reloaded a draft, scheduled and paused it, explicitly approved a mocked delivery, and observed the published record. It then checked 14 workspace routes at 1440, 834 and 390 pixels, with 42 screenshots, no detected horizontal overflow, and a working mobile navigation drawer. The screenshot-heavy test took 57 seconds; its timeout was raised after an earlier run exceeded 45 seconds.

## How to reproduce

Use the separate browser fixture and ports described in README.md. Browser results are written to frontend/test-results/results.json; viewport captures are under frontend/test-results/screenshots. Backend tests are in backend/tests. The browser fixture creates only its own database, and must not be deployed.

## Verification boundaries

An automated pass does not establish product approval, live consent, real API delivery, or LinkedIn engagement counts. Live LinkedIn, SMTP delivery and optional AI require operator configuration. Production hosting, PostgreSQL, multi-instance load, external monitoring, every assistive technology, and all individual legacy controls were not tested. The responsive checks verify representative interactions and page width; they are not an accessibility certification.

