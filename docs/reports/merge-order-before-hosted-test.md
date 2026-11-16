# Merge order before the hosted proxy test

State on 16 Nov 2026. `main` already holds the diagnostics (#10) and the sign-in selectors (#11). Nothing below is pushed yet.
Railway redeploys the API and the worker by itself when `main` changes. The frontend on Vercel does NOT: after the last
frontend merge, I trigger a production deployment of `main`.

| Order | Local branch | Why it must (or need not) be in before the test | Base now | Tested locally |
|---|---|---|---|---|
| 1 | `fix-controls-timezone-test` | Settings page no longer overwrites a typed time zone; removes the one real CI failure, so the later merges can go green | old `main` (needs a rebase) | see report |
| 2 | `profile-read-fix` | **Required.** Without it a hosted sign-in or reconnect reaches the logged-in page and then times out on the profile name. Also holds `session_reuse_check` and the probe's confirmation prompt | current `main` | 79 sign-in tests pass |
| 3 | `new-accounts-start-stopped` | **Required before another account is connected.** A new account starts at limit 0, not 50 | old `main` (needs a rebase) | see report |
| 4 | the connect-panel branch (in progress) | Optional for the proxy test. Elapsed time is already live; this adds refresh-resume, clearer wording, Connect Another, and removes the time zone field | `main` | in progress |
| 5 | `roadmap-outflo` | Documentation only; no effect on the test | old `main` (needs a rebase) | n/a |

The proxy test itself needs only **2** (and **1** to keep CI green). The proxy field, the proxy test and the Check button already
exist in the merged code. Branches 1, 3 and 5 sit on the old `main`: I rebase each onto the current `main` before it is pushed, so
the pull requests are small and merge cleanly. Push one at a time, in this order, waiting for CI to pass on each.
