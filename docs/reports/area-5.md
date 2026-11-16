# Area 5: Campaigns and AI writing (report)

Date: 2026-11-16. Branch `local-complete`. Local only; nothing pushed or deployed.
Source: OutFlo report sections 1, 2 and 7, gap items 1 to 6. Checklist lines 5.A to 5.L in `docs/CHECKLIST.md` (108 lines: 65 done, 17 partial, 26 open).

**This area is not finished.** The linear (Classic) builder, the AI writing and the launch gate are built and tested. The Smart graph builder with branches, the extra action types, and voice notes are not built; they are listed under "Open" with the reason.

## Table

| Item | Status before | What I did | Test | Result |
|---|---|---|---|---|
| Campaigns list: columns, status filter (7 statuses plus archived), accounts filter, name search | Partial (a sortable table) | Rebuilt with the report's columns and the status a person reads (queued, running, no more pending actions, failed come from the real runs) | campaigns-list.spec (8); test_campaign_list | pass |
| Row menu: duplicate, share sequence, archive (off for a draft), delete with confirm | Missing | Backend actions and menu; the shared file holds steps and context, never leads, senders or runs | campaigns-list.spec; test_campaign_list RowActionsTest | pass |
| Builder shell: name, Save draft, autosave and its indicator, unsaved-changes prompt, four steps | Partial (one page that created and launched in one go) | New four-step wizard; a draft is created when you open it; saves as you go | campaign-builder.spec (11) | pass |
| Builder opens with no sender and no leads | Works | Kept; every missing thing appears in the launch checklist | campaign-builder.spec; test_launch_check | pass |
| Step 1 senders, limits shown, total, View limits, per-sender action allocation | Missing | Table, totals and an allocation drawer (clamped to the hard maximum); the engine obeys the reserved slice | campaign-builder.spec; test_campaign_settings AllocationTest | pass |
| Step 2 leads | Partial | List picker plus Add leads (all area 4 sources) | builder spec | pass |
| Step 3 Classic sequence: connection note (200 characters), If connected, waits, message, follow-ups, remove | Partial (flat list) | Blocks show their settings; waits have minimums | campaign-builder.spec 'the sequence' | pass (reordering not built) |
| Message variables: lead, linkedin_*, sender_*, custom, spintax, chips | Partial (lead fields only) | linkedin_* names added; sender_* filled once the sender is known (at send time and in the dry run) | test_message_variables (5) | pass |
| Message preview (sender, lead, shuffle, missing-variable warning) | Missing | Render endpoint and dialog | test_message_variables; no UI test of the dialog | built, UI test open |
| AI drawer per message: Direct or AI assisted, tone, strategy, instructions, honest profile options, preview with cost, regenerate, unsaved prompt | Missing | Drawer, prompt builder, validation | campaign-builder.spec 'AI writing'; test_ai_writing (10) | pass |
| Profile data the AI reads: recent posts, skills, career, interests | Missing | Disabled "coming soon": they need a paced profile reader. The server refuses them. Current role and company work. | test_ai_writing | partial, by design (no inert switch) |
| AI campaign context: Upload, Context, Guardrails, templates, meeting link, do-not-mention | Missing | Panel and storage; the AI uses only what is written there | campaign-builder.spec 'AI campaign context'; test_ai_writing | pass (PDF and Word not read; website saved, not read) |
| Providers: Deepgram default, local Ollama option, template fallback | Partial (Deepgram or template) | Ollama provider and `AI_PROVIDER`; the estimate says which one and what it costs | test_ai_writing OllamaTest | pass (no settings screen yet: area 8 and 10) |
| AI drafts written before launch with the cost shown, reviewed and approved | Works | Only AI-assisted steps get drafts; the launch is blocked until every AI message is written and approved | test_launch_check; builder spec | pass |
| Step 4: weekly schedule with time zone and Apply to all | Partial (one window) | Per-weekday hours enforced by the engine | test_campaign_settings ScheduleTest; builder spec | pass |
| Exclusions (5 toggles plus the locked do-not-contact list) | Missing | Enforced at launch with counts per reason; the dry run shows who is left out and why | test_campaign_settings ExclusionTest; test_launch_check DryRunTest | pass |
| Launch checklist: no sender, no leads, empty message, AI messages missing or unreviewed, bad hours; each with its own message and the step that fixes it | Partial | `GET /campaigns/{id}/launch-check`; the Launch button says "Fix N things to launch" | test_launch_check (7); builder spec | pass |
| Dry run | Works | Shown in the review step | builder spec 'dry run' | pass |
| Smart (graph) builder, its nodes, conditionals, templates | Missing | **Not built.** Shown as disabled "Smart" with the reason | none | open |
| Extra actions: follow profile, like a post, view profile, InMail, free InMail, withdraw invite | Missing | **Not built** as nodes. Follow and view profile exist as worker actions but have no builder node. Like, InMail and withdraw need worker actions, ceilings and mock pages | none | open |
| Voice notes (record, upload, AI script, voices, accents) | Missing | **Not built.** Voices are assigned per account (area 3); Piper is not installed | none | open |
| Sequence templates and previous-campaign reuse | Missing | Share-sequence file exists; applying a template is area 9 | none | open |

## Verification
- Backend: new this area: test_campaign_settings 8, test_ai_writing 10, test_launch_check 7, test_message_variables 5, test_campaign_list 5. test_outreach (89) and test_prepared_messages pass after the engine changes. Full suite result is in the handover.
- Playwright (dev server): campaign-builder 11, campaigns-list 8, app-shell 17 pass. Axe and 360 px pass for every builder state (senders, leads, sequence, review, AI drawer, context panel) and the list, both themes. Screenshots for area 5 are not yet captured or viewed.
- Real LinkedIn: nothing run. No action in this area touches LinkedIn except through the existing worker.

## Open (carry to the next stretch)
1. **Smart graph builder and engine branching.** Plan: a tree (each node has one next, conditionals have two branches), stored as steps with `parent_step_id` and `branch_condition`; the engine takes the child by outcome; "If connection" and "Is active on LinkedIn" as conditional nodes; a 15-day wait on the not-connected branch. Risk: the linear engine is covered by 89 tests, so branches must be added behind the classic path.
2. Extra action nodes and their worker actions, ceilings and mock pages.
3. Voice notes (Piper install, script, record or upload, preview with cost).
4. Per-profile reader as paced tasks (recent posts, skills, career, interests) so those AI options can be switched on.
5. Reordering of sequence blocks; follow-up waits shorter than one hour; a UI test of the message preview dialog; keyboard walk-through test of the builder.
6. The flaky draft-generation test (not reproduced yet; run 20 times after a fix).

## Standing reminders
- Secret scan broken in CI (deferred by the owner on 15 Nov 2026; must be fixed and run on full history before any public repo or real user).
- Clerk secret and CockroachDB password were exposed in chat on 15 Nov 2026 (rotation deferred; mandatory before any real user, pilot, production deploy or public repo).
