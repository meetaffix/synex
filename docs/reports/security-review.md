# Security review of the new surfaces (16 Nov 2026)

Scope: webhooks and Slack, API keys, the public API and MCP server, CSV and file uploads and exports, logs. Method: read the code, fix what was found, add a regression test per protection, then remove each protection in turn (mutation check) to confirm a test fails. Tests: `backend/tests/test_security_surfaces.py` (19 tests, all pass).

## Findings and fixes

| # | Surface | Finding | Fix | Test that fails without it |
|---|---|---|---|---|
| 1 | Webhooks | Redirects were followed, so a public address could bounce a call to a private one. | No redirect is followed; a 3xx answer is reported as a failure. | `test_a_redirect_is_never_followed` |
| 2 | Webhooks | The private-address check ran only when the webhook was saved. DNS can change afterwards. | The address is checked again at every call. | `test_the_address_is_checked_again_when_the_event_fires` (the pinned-connection check below also covers this path) |
| 3 | Webhooks | DNS rebinding: the name was resolved once for the check and again for the call. | The call connects to the address that was just checked; the certificate is still verified for the real host name. | `test_the_call_connects_to_the_address_that_was_checked` |
| 4 | Webhooks | The block list missed carrier-grade NAT, multicast, unspecified and IPv4-mapped IPv6 addresses, and passed a name when only one of its answers was private. | A name is refused unless every answer is a public address (`is_global`). | `test_every_dns_answer_must_be_public` |
| 5 | Webhooks | A username or password in the address was accepted. | Refused. | same test |
| 6 | Webhooks | No retry policy. | 3 attempts at most, only for a network failure, a 5xx or a 429; 10 second timeout; every attempt is recorded. | `test_retries_stop_after_the_limit...`, `test_a_slow_receiver_is_given_up_on` |
| 7 | API keys | One permission level: any key could create leads. | Scopes `read` and `write`. New keys are read-only unless "Allow adding leads" is ticked. Keys made earlier are read-only. | `test_a_key_reads_by_default...`, `test_a_key_made_before_scopes_existed_is_read_only` |
| 8 | API keys / MCP | No rate limit. | 60 requests a minute per key, shared by the public API and MCP, with `Retry-After` on a 429. | `test_each_key_has_its_own_rate_limit`, `test_the_window_slides` |
| 9 | CSV exports | Neutralisation of text that starts a spreadsheet formula was copied into five places, missed some columns (email, phone, profile link) and the tab and carriage-return starters. | One function, `app/csv_safe.py`, used by every export. | `test_every_formula_starter_is_neutralised`, `test_every_export_neutralises...` |
| 10 | CSV imports | Three importers had no row limit and none refused binary content. | A shared parser: 10,000 rows (5,000 for do-not-contact), no NUL bytes, size cap by the request model. Errors are 422 with a plain message. | `test_an_import_is_limited_in_rows_and_refuses_binary_content` |
| 11 | Logs | Not checked. | A runtime test captures every log line while keys, webhooks, imports and leads are used and asserts no key, secret, Deepgram key or email appears. A static test fails if any logging call passes a variable named password, secret, token, cookie or similar. No offender was found. | `LogHygieneTest` |

Already correct and now under test: keys are stored only as a SHA-256 hash and shown once; a revoked key stops at once; `last used` is recorded; every public API and MCP read is filtered by the key's own workspace (`IsolationTest`); MCP offers no tool that changes data; webhook signatures use HMAC-SHA256 over the exact body.

## Mutation check

Nine protections were removed one at a time and the suite re-run. Eight were caught by the test named for them. One survived: removing the fire-time address check alone changes nothing, because the pinned-address step right after it refuses the same call. The two checks back each other up, so this is accepted.

## Still open (not fixed, with reasons)

1. **Webhook signing secrets are stored as plain text** in the database, because Synex must sign with them. Encrypting them at rest with the existing Fernet key is a small, safe change; it is queued for area 12.
2. **The rate limit is kept in memory per process.** With one API process it is exact. If the hosted API runs several processes, each has its own window, so the real limit is the number of processes times 60. Moving the counter into the database is needed before scaling out.
3. **No limit on failed key attempts.** A key has 256 bits of randomness, so guessing is not realistic, but a flood of bad keys still costs a database read each. A per-address limit belongs in the hosting layer.
4. **Google Sheets import follows Google's own redirects** from a fixed `docs.google.com` address. The start address is fixed, so it cannot be pointed elsewhere.
5. **Not reviewed here:** the assistant relay, Clerk sign-in, and the LinkedIn session code. Those belong to the full security review before any public release.
