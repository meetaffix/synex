# Decisions taken while the owner is away

Format: what, why, alternatives. Newest at the bottom.

1. **Checklist area = ID prefix; "Done" = every line ticked.** Counted by `tools/checklist_status.py`. Why: the owner asked for a truthful, reproducible status. Alternative: manual counts (error-prone, rejected).
2. **LinkedIn-dependent lines carry `[LV:mock]` or `[LV:real]`.** Why: separate "tested on the mock site" from "verified on real LinkedIn". Alternative: a separate document (would drift).
3. **Real LinkedIn is not touched while the owner is away.** The six read-only tests stay in `docs/reports/real-linkedin-read-only-plan.md`.
4. **withdraw_invite got its own hard ceiling of 20 a day.** Why: every action type needs one, and withdrawing is a LinkedIn action. The agreed-ceilings test now lists it.
