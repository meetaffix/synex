# Area 6: Inbox (report)

Date: 2026-11-16. Branch `local-complete`. Local only; nothing pushed or deployed.
Source: OutFlo report section 3 and gap item 8, plus our extras. Checklist lines 6.01 to 6.29 (29 lines: 22 done, 7 partial, 0 open).

## Table

| Item | Status before | What I did | Test | Result |
|---|---|---|---|---|
| Three panes: list, thread, profile panel; "Select a conversation" | Partial (two panes) | Added the profile panel; the list and thread kept | inbox.spec (11) | pass |
| Search all conversations (name, company, message text) | Partial (name, company) | Server-side search incl. message text | test_inbox FilterTest | pass |
| Date presets and custom range | Missing | Seven presets, custom range with From and To | inbox.spec; test_inbox | pass (preset arithmetic has no unit test) |
| Needs my reply, I messaged last | Missing | Derived from the last message and an "answered" flag that resets when the person writes again | test_inbox FilterTest | pass |
| Status: starred, drafts, scheduled, unread; archived | Partial (unread) | All as real filters | test_inbox; inbox.spec | pass |
| Tags (custom), system tags | Missing | Custom tags (10 per conversation, 40 characters); system tags are the five interest labels | test_inbox BulkTest; inbox.spec | pass |
| Sender accounts: chips and filter | Missing | Chips beside the header | inbox.spec; test_inbox | pass |
| Campaigns include or exclude, "include where messages sent or responses" | Missing | Server filters and panel controls | test_inbox FilterTest | pass (no browser test of these two controls) |
| Conversation card: account, needs-reply, interest, scheduled, tags, draft, star, checkbox | Partial | Rebuilt | inbox.spec | pass |
| Bulk actions: read, unread, star, archive, tag, interest | Missing | Bulk bar and endpoint | inbox.spec; test_inbox BulkTest | pass |
| Reply: send, draft saved as you type, sending-from, read-only notice | Missing (the box was disabled) | Replies queue through the normal send path and its limits | inbox.spec 'reply'; existing send tests | pass |
| Schedule message | Missing | Stored, listed, cancellable; due messages go through the normal send path and are checked against limits at that moment; a failure shows its reason | test_inbox DraftScheduleTest; inbox.spec | pass |
| AI suggested reply with its cost shown first | Missing | Written from the thread and the campaign's AI context, saved only as a draft, never sent | test_inbox SuggestTest; inbox.spec | pass |
| Interest labels | Missing | Five labels, filter and bulk set | test_inbox; inbox.spec | pass |
| Emoji | Missing | Small emoji row | inbox.spec (visible only) | pass |
| Attachment, voice message | Missing | Disabled "coming soon" | inbox.spec | not built |
| Profile panel: details, star, answered, archive, interest, tags, lead overview, add to campaign | Missing | Built; "Fetch profile" is disabled "coming soon" (needs the paced profile reader) | inbox.spec | pass (fetch open) |
| Refresh and live sync | Missing | Refresh queues one paced inbox read per connected sender under the inbox ceiling (never the outreach limits, never two at once); the list polls every 30 seconds and shows the last read time | test_inbox ExportRefreshTest; inbox.spec | pass |
| Export CSV with the current filters | Missing | CSV export, spreadsheet formulas neutralised | test_inbox; inbox.spec | pass |

## Verification
- Backend: test_inbox 18 tests pass. Full suite last run: 445 tests, 0 failed (before this area); a final run is part of the end-of-build check.
- Playwright (dev server): inbox.spec 11 pass; axe and 360 px pass for inbox-no-account, inbox-empty, inbox-thread and inbox-filters-and-bulk, both themes.
- Screenshots in `docs/reports/screens/area-6/` (both themes, 360, 768, 1280). I looked at the thread at 1280 light: three panes, reply tools and profile panel fit. The list items were captured mid-animation, which is a capture-timing effect, not a bug.
- Real LinkedIn: nothing run. Reading inboxes uses the existing worker action (unverified status unchanged).

## Open
1. Attachments and voice messages in replies (disabled).
2. Fetch profile in the profile panel (needs the paced profile reader).
3. Browser tests for the campaign include/exclude and "include where" controls, and a keyboard walk-through test.
4. Hosted database: new table `scheduled_messages`; new `conversations` columns `starred, answered, tags, interest, draft_body` (added by `run_simple_migrations`).

## Standing reminders
- Secret scan broken in CI (deferred by the owner on 15 Nov 2026; must be fixed and run on full history before any public repo or real user).
- Clerk secret and CockroachDB password were exposed in chat on 15 Nov 2026 (rotation deferred; mandatory before any real user, pilot, production deploy or public repo).
