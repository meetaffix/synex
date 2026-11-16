# Decisions taken while the owner is away

Format: what, why, alternatives. Newest at the bottom.

1. **Checklist area = ID prefix; "Done" = every line ticked.** Counted by `tools/checklist_status.py`. Why: the owner asked for a truthful, reproducible status. Alternative: manual counts (error-prone, rejected).
2. **LinkedIn-dependent lines carry `[LV:mock]` or `[LV:real]`.** Why: separate "tested on the mock site" from "verified on real LinkedIn". Alternative: a separate document (would drift).
3. **Real LinkedIn is not touched while the owner is away.** The six read-only tests stay in `docs/reports/real-linkedin-read-only-plan.md`.
4. **withdraw_invite got its own hard ceiling of 20 a day.** Why: every action type needs one, and withdrawing is a LinkedIn action. The agreed-ceilings test now lists it.
5. **New API keys are read-only by default; keys without a recorded scope are read-only.** Why: least privilege; an old key silently losing write access is safer than one gaining it. Alternative: treat old keys as read and write (rejected).
6. **Webhooks connect to the checked IP address and refuse redirects.** Why: stops DNS rebinding and redirect SSRF. Alternative: re-resolve at call time only (leaves a small rebinding window).
7. **Rate limit is in memory, 60 a minute per key.** Why: simplest correct limit for one API process; recorded as a limit in the security review for multi-process hosting.
8. **The real typecheck is `npm run typecheck` (tsc -b).** An earlier habit of running `tsc --noEmit` at the project root checked nothing (the root tsconfig lists no files), so reports of "typecheck passes" for areas 5 to 10 were wrong. 28 real errors (zod 4 `z.record` needs two arguments, a Switch missing a prop) were fixed on 16 Nov 2026 and `tsc -b` now passes. Every later report states the exact command.
