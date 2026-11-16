# Real LinkedIn, read-only verification: the one GO request

Account: Meet Affix only. All six tests only READ. Nothing is sent, withdrawn, followed, liked or changed. The owner types the password and any code. Every step stops at once on any LinkedIn warning, checkpoint or restriction. Gaps between page loads are random, 8 to 25 seconds. Total volume across all six: about 40 page loads, in one sitting of roughly 15 minutes. Each uses its own read ceiling (sync_inbox, sync_connections, collect_leads, visit_profile), never the outreach budgets, and none runs more than once.

| # | Test | Exactly what is read | Volume |
|---|------|----------------------|--------|
| a | Inbox sync | The conversation list, then ONE thread (the first), nothing marked read by Synex | 2 page loads |
| b | Connections list and received invitations | First page of my connections, first page of received invitations | 2 to 4 page loads (scroll limit 20 rows each) |
| c | Profile reader | ONE profile you name: headline, photo, current company | 1 page load |
| d | Post reactions | ONE post you name: the reactions list, limit 20 people | up to 3 page loads (limit 20) |
| e | Basic search collection | ONE search link you name: first page of results, limit 20 | up to 3 page loads (limit 20) |
| f | Pending-invite page | The Sent invitations page, view only. The Withdraw button is located, never clicked | 1 to 2 page loads |

Inputs I need from you with the GO: the post link for (d), the search link for (e), the profile link for (c).

For each test, after it runs: the page is captured (HTML with personal text removed, plus a screenshot kept only on this computer, never committed), selectors are fixed from the capture, the mock site is changed to match, tests are added, and the checklist line is marked "verified on real LinkedIn". I will report what differed from the mock.

Reply "GO" to start all six, or "GO except X" to drop any.
