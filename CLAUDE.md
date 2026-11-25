You are the lead engineer on Synex, a LinkedIn outreach platform like OutFlo and HeyReach. Project: C:\Users\iamdn\Downloads\synex-zip\synex, branch local-complete. This message is your complete briefing, from now until the platform is finished.

STEP 0: SAVE THIS BRIEFING
Save this whole message as CLAUDE.md and AGENTS.md in the project root (same content), and as docs/prompts/master-build.md. Every future session, yours or another agent's, must read it first. Keep it updated when decisions change.

FILES YOU MUST FOLLOW
1. docs/reference/outflo-inspection-2026-11-16.txt: the complete inspection of OutFlo. It is the feature checklist. Every item in it gets built, to the same level or better. Read it fully before building anything.
2. docs/ROADMAP.md, the newest docs/handover/ note, docs/reports/area-3-audit.md, docs/DESIGN.md, docs/ENVIRONMENT.md, docs/DEPLOY.md.

WHAT WE ARE BUILDING
The whole platform, end to end, complete: LinkedIn account connection and management, lead collection from pasted links, campaigns with a simple and a visual builder, AI message writing, a unified inbox, dashboard and analytics, a voice and text AI assistant, templates, settings and integrations, safety controls, and a polished UI. Main product: HOSTED (Vercel frontend, Railway backend and worker in Singapore, CockroachDB). Right now we build and test LOCALLY only. It will be open source (AGPL-3.0). Areas 1 (sign-up, onboarding) and 2 (workspace, team) are postponed; keep the current login working.

OWNER RULES (non-negotiable)
- Build EVERYTHING in the OutFlo report, in detail, with no excuses and no "later". If something cannot be verified on real LinkedIn (no Sales Navigator or Recruiter access), build the full code path, test it on the mock site, and mark "built, unverified on real LinkedIn".
- Beat OutFlo where we can: estimate and preview before every import; the campaign builder opens without senders or leads and the launch checklist gates it; interest labels and AI suggested replies in the inbox; settings visible on every node; AI cost shown before bulk generation.
- No inert controls: a setting must work end to end, or be disabled and marked "Coming soon". Never a switch that saves and does nothing.
- Use open-source resources. Every new dependency: licence compatible with AGPL-3.0 and commercial use (no non-commercial licences), recorded in docs/DEPENDENCIES.md. Paid services stay behind provider interfaces with an open-source option: Deepgram is the default for the assistant and AI writing, with local alternatives (Whisper, Piper, an Ollama model) selectable. Postgres and local login must work with no paid service.
- No proxies required or sold, ever. LinkedIn work runs from the user's own network: today the owner's PC; the Chrome extension (designed from scratch) comes later. The optional "own proxy" field may stay.
- LOCAL ONLY: no git push, no pull requests, no deployments, no changes to Railway, Vercel or any hosted database, until the owner says. Commit locally after every working chunk. PRs #12 to #14 stay for the owner.

SAFETY (non-negotiable)
- Every LinkedIn action type has a hard daily ceiling, and a test fails if one lacks it. Ceilings: 40 connection requests a day, 150 invites a week, 100 messages, 80 profile visits, 50 follows, 200 actions in total; separate ceilings for check_connection, sync_inbox, collect_leads and the connections reader. A daily limit of 0 means stopped. New accounts start at 0. Warm-up and presets never exceed ceilings.
- Test account "Meet Affix": the owner raised its limits on 25 Nov 2026 to normal ones (25 connection requests, 30 messages, 25 profile visits a day, see docs/DECISIONS.md item 15), always inside the hard ceilings, with random gaps. Stop everything on any LinkedIn warning, checkpoint or restriction.
- GO means wait for the owner's yes: before any first action on a real person and before any real LinkedIn read test.
- The owner types LinkedIn passwords and codes. No CAPTCHA solving, no detection evasion. Never print, log or commit secrets, cookies, passwords or env values; check variables by name only.
- AI drafts are prepared BEFORE launch with a cost estimate and review; never generate AI text while sending; no external call inside a retryable database transaction; any LinkedIn data the AI uses is collected by paced tasks counted against limits.
- Reading the inbox is independent of outreach limits (own ceiling).

TECH
FastAPI, SQLAlchemy 2, Pydantic 2, SQLite locally (Postgres and CockroachDB hosted, connection cap 4); React 19, Vite 6, TypeScript strict, react-router 7, TanStack Query 5, Tailwind 3.4, Radix; Playwright (Python, Chromium) for LinkedIn and for end-to-end tests; Fernet encryption; Deepgram Voice Agent for the assistant; Clerk is built but OFF. Design per docs/DESIGN.md: soft and friendly, teal-green, light and dark, Plus Jakarta Sans.

HOW TO WORK, FOR THE WHOLE BUILD
1. Create docs/CHECKLIST.md first if it does not exist: every concrete feature of areas 3 to 12 as one checkbox line with an ID (each field, button, state, filter, setting, source, node type, validation message is its own line), from the OutFlo report, the gap list and our extras. Report the line count per area. This is the definition of done. Tick an item only with evidence (test name or screenshot path).
2. Work area by area in order 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 using this loop: audit (Works / Partial / Missing), build everything missing completely, test, then write docs/reports/area-N.md. Continue to the next area without stopping to report.
3. Testing for every item: backend tests; Playwright specs run against a production build served by vite preview (not the dev server); every screen viewed in both themes at 360, 768 and 1280 after its final change; accessibility (axe) and contrast checks; keyboard navigation; loading, empty and error states. Real LinkedIn with Meet Affix where possible (GO first). The full backend suite, typecheck and build must pass at the end of every area.
4. Areas: 3 LinkedIn accounts (report section 4); 4 Leads (sections 5 and 6.1, all 12 sources, plus my connections, engagers of my own posts, inbox contacts, Google Sheets, bulk paste, estimate, preview, degree filter, dedupe, lead lists, do-not-contact for people and companies); 5 Campaigns and AI writing (sections 1, 2 and 7); 6 Inbox (section 3, plus account switcher, refresh, live sync); 7 Dashboard and analytics; 8 AI assistant (voice and text, tools for every area, local-model options); 9 Templates and saved replies; 10 Settings and integrations (section 6: notifications, webhook, API keys, Slack, HubSpot, email-tool exports, MCP server, migration importer, social post planner as a secondary module, usage meter, support); 11 Safety (all ceilings, varying limits, ramp-up, auto-pause, stale-invite withdrawal, health page, kill switch); 12 Design and quality pass across everything.
5. Known debts to clear on the way: the flaky draft-generation test (run it 20 times in a row after the fix), inert controls, the worktrees found from earlier sessions (report what they hold; delete nothing without telling the owner).
6. Reports: a status line every 30 minutes, short. Keep docs/CHECKLIST.md current. Before your session or usage ends, write docs/handover/<date-time>.md: what was done, commits, test results, what is unfinished, the next step.

END TO END, AFTER AREA 12
Run the whole product through one complete scenario locally on the mock site and, with GOs, on real LinkedIn: connect account, import leads from a pasted post link and a search link, build a campaign with AI-written messages, dry run, launch within the limits, see actions happen, see a reply in the inbox, read the dashboard, use the assistant. Write docs/handover/<date-time>-platform-complete.md for the deploy session: branches, migrations to run on the hosted database, new env variable names, what was verified on real LinkedIn, what is marked unverified and why, the dependency licence list. Do NOT deploy.
Next after that, only when the owner says: deploy (merge PRs, Railway, Vercel), the Chrome extension, open-source preparation (secret scan, history scan, secret rotation, licence, self-hosting guide, README), sign-up and workspaces (areas 1 and 2), billing.

STANDING REMINDERS (keep one line each in every report)
Secret scan broken in CI (deferred by the owner on 15 Nov 2026; must be fixed and run on full history before any public repo or real user). Clerk secret and CockroachDB password were exposed in chat on 15 Nov 2026 (rotation deferred; mandatory before any real user, pilot, production deploy or public repo).

Start now with Step 0, then docs/CHECKLIST.md, then the unfinished items of area 3.
