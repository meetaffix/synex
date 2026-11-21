# Synex audit, part 2: every way a campaign starts, and every screen (21 Nov 2026)

Part 1 is `audit-2026-11-21.md`. How this part was done: I opened each screen of the running app in the built-in browser (read-only: no launch, send or save
clicked) and read the code behind each launch path.

Screens walked: Dashboard, Inbox, Campaigns (list, campaign page, edit sequence), Sender accounts (list and account page), Leads (Contacts tab), Templates,
Others, Content publishing (Overview, Queue), Settings, Integrations, Safety, Audit log, Help.

**Not walked**: Leads > Lists, Companies, Do not contact; the "Add leads" dialog; the new-campaign wizard steps 1 to 3 (opening `/campaigns/new` creates a
draft campaign by itself, see L9, so I did not open it); Studio, Calendar, Activity, Engagement, Analytics and Connections in publishing; phone-width layouts;
dark theme. Whatever is not listed above is "not verified".

## A. Every way a campaign starts sending

| # | Path | What it does today | Problem | Fix |
|---|---|---|---|---|
| L1 | Builder step 4, "Launch campaign" (`ReviewStep.tsx`, sets `status=active`) | Runs the launch checklist, enrols every lead, stamps `launched_at`. | The dry run ("Preview what would be sent") is optional. The only confirmation is a generic checkbox "I confirm all details are correct". The first real send to real people is never shown as recipient plus exact text. | Make the dry run a required step on first launch; show recipients and exact text in the confirm. |
| L2 | Campaign page, **Resume** button (`CampaignPage.tsx:106`) | One click sets `status=active` through the same update call; `launch_campaign` runs again and silently enrols any lead added to the list while paused. | No confirmation, no preview, and new people can start on resume. | Confirm dialog: how many people will be enrolled and who is sent first. |
| L3 | Campaign page > Edit sequence > Save, on a running campaign | Changes go live at once for people not yet on those steps. | Only step text is validated. The toolbar has a red **Clear all** next to Full screen on a live campaign. | Hide Clear all while running; show a diff before Save. |
| L4 | Lead > "Add to campaign" (`routers/leads.py::add_to_campaign`) | Appends the lead to the list and, if the campaign is active, starts their sequence at once. | Skips the launch checklist, no preview, no confirm. | Same confirm as L2, re-run the launch checks. |
| L5 | Failed-run **Retry** and **Skip** (`routers/campaigns.py::_run_action`) | Frees the idempotency key and puts the run back to running; the next worker cycle sends. | This is what put the three live-test sends due at 11:09 UTC on 21 Nov: Retry started real sends with no preview. | Retry shows recipient and text and needs a confirm. |
| L6 | Assistant "resume campaign" (`assistant/tools.py`) | Confirmation card; first launch is blocked; resume is allowed. | Same enrolment on resume as L2. | Same as L2. |
| L7 | Smart (map) builder and Classic builder | Same endpoints, same checks. Smart starts empty on purpose. | None found in code. Not exercised in the browser. | - |
| L8 | Duplicate, Import sequence, share link | Create a draft. | Not read in depth. Not verified. | - |
| L9 | Opening `/campaigns/new` | `NewCampaignPage.tsx` posts "Untitled campaign" as soon as the page opens. | A page view creates database rows; a refresh or a React double render can make extras. | Create the draft on the first real edit, or reuse an empty one. |
| L10 | Defaults for a campaign created without the builder (API, assistant) | `_create` uses time zone America/New_York, 09:00 to 17:00 Mon to Fri, 20 requests and 40 messages a day. The builder uses the browser time zone and 08:00 to 20:00. | For a sender in India the API default sends at night or not at all; the two defaults disagree. | One default, taken from the sender's time zone. |
| L11 | Removing a lead from a campaign's list | `launch_campaign` is the only code that reads the list; `_advance_run` never checks the lead is still on it. | A person taken off the list keeps getting messages. | Stop the run when the lead leaves the list. |
| L12 | The same person in two campaigns | All five exclusions (`other_campaigns`, `reached_other_campaigns`, `reached_same_sender`, `messaged_other_senders`, `existing_connections`) default to off (`campaign_settings.DEFAULT_EXCLUSIONS`). | A person can get two sequences, or messages from two senders, by default. | Default `other_campaigns` and `messaged_other_senders` to on. |
| L13 | `campaigns.audience_source` | The UI never writes it (only a TypeScript type mentions it). The engine rule "My connections = already connected" and the launch check that skips the connection-request requirement both read it, so both are dead for UI-built campaigns. This campaign holds the string `'null'`. | Connections only work through each lead's degree and status. | Set it when the list comes from My connections, or remove the rule. |

## B. Screen by screen: wrong or misleading information

| # | Screen | What is shown | Why it is wrong or confusing | Fix |
|---|---|---|---|---|
| U1 | Sender accounts list and account page | "Last 24 hours: 0 connection requests, 1 messages", "Messages 1 of 4 to 5", "Used today: 1". | `account_policy.rolling_usage` counts `pending` and `running` tasks, so a message that is only queued shows as sent. When I looked the `messages` table was empty and the task was still `pending`. | Show queued and sent separately. |
| U2 | Dashboard header | "1 action sent today, 0 replies waiting." | Same cause as U1. The funnel on the same page says Contacted 0. | One source of truth. |
| U3 | Sender accounts list | "Accepted 100%" for an account with 0 connection requests. | A percentage of nothing. | Show "No data". |
| U4 | Account page: "Inbox reads 11 of 11" | The day's inbox budget is already used. The last read in the database is 10:23 UTC. | Nothing can read replies until it frees up, so a reply to the live campaign would not be seen. My earlier fix spaces future reads but cannot give back the used ones. | Give inbox reads their own budget outside the outreach limits, as the product rules say. |
| U5 | Audit log | "send message, ok, Not connected yet, so the message waits." for two attempts that failed and sent nothing. | Wrong result and wrong reason. "Who" is the sender account, never the recipient, so the log cannot say whom a message was for or what it said. Raw error names ("Retry timeouterror"). 33 rows, mostly inbox reads, bury real sends. | Record recipient and text; show failures as failures; default the filter to sends; plain error text. |
| U6 | Campaign page, "What is happening" | "Everything is running normally. Last: nothing yet." after two failed sends. | The first failure is stored as `cancelled`, which no health check counts. | Count cancelled-with-reason as needs attention. |
| U7 | Dashboard hero card | A large card titled Reply rate: "Not available yet. It appears once ... the dashboard feed is connected." | Developer wording; takes the top of the page for nothing. "Not available yet" repeats about ten times (response time, each cell of the sender table). | Show a dash and one hint line. |
| U8 | Dashboard checklist | "You are set up. Every step is done." | True before anything has been sent; reads as success. | Show only while something is missing. |
| U9 | Dashboard | Median response time, Interested leads answered, Funnel, By campaign and Sender accounts tables, each with its own export. | Seven blocks for 3 leads and no activity. | Collapse empty sections. |
| U10 | Settings (one very long page) | Profile, password, "LinkedIn sign-in: Not linked", "LinkedIn OAuth configuration: Not configured", "Publishing worker: Healthy", "Writing assistance: Configured", Resources, Plan with a four-plan comparison and "Change plan (not available yet)", Assistant, local model, "Ask the local assistant". | Publishing and outreach diagnostics mixed into account settings; a plan comparison for plans nobody can buy; the assistant card repeats Deepgram, Ollama, Whisper and Piper status lines. | Split into Account, Security, Assistant; move publishing diagnostics under Publishing. |
| U11 | Sender accounts | Plan card: Plan Pro, Seats 1 of 15, Seats available 14, "Manage plan: Coming soon: Synex does not sell plans yet". | A billing box for something that does not exist. | Remove until billing exists. |
| U12 | Account page | Four ways to set limits: "Test account profile", the used/limit/range table, "Daily sending" (three sliders plus Careful/Steady/Fast), "Advanced: set every action yourself". The test profile promises 5; the table says "Today's limit 4, range 4 to 5". | The same limits are editable in three places and the shown number (4) does not match the promised one (5). | One table; pick the day's number once and show it. |
| U13 | Content publishing | Queue page: "Connection requests, direct messages, scraping, and automated engagement are not executed by this app." Overview asks to "Connect LinkedIn / Authorize your LinkedIn account". | The first sentence is false for this product (left over from a publishing-only build). The second is a second, separate LinkedIn connection (OAuth) next to the sender session. | Reword; say publishing uses a different connection. |
| U14 | Safety page | Kill switch: "Only a platform administrator can use the kill switch." | On a local one-person install the owner cannot reach it. | The owner of a local install is the administrator. |
| U15 | Inbox | Header "Last read about 2 hours ago"; empty state "Conversations appear here once a lead replies". | The read is not running (U4) and nothing says so. | Show "Inbox reads paused: limit used". |
| U16 | Campaign list | Status filter offers Queued, "No more pending actions", Failed. | A campaign with a failed attempt still reads "Running". | Show failures in the row. |
| U17 | Campaign page | "Coming up" shows "Today, 12:09 PM" for all three leads. | All three are due at one instant; per-account pacing happens later, so these are not real send times. | Say "Next" without a time, or show the account's next slot. |
| U18 | Navigation | Seven sidebar items plus Others, which holds two cards (Lead Lists, Content publishing). Leads has four tabs, one of which (Lists) is also reachable from Others. | Same screen under two menus. | Remove the Others card for lists. |

## C. Clutter list (candidates to remove or hide)

Plan comparison and seat counters; the Pro/Demo/Scale/Enterprise table; the "Resources" block in settings; publishing diagnostics in Settings; the test-profile
card plus the Advanced policy (keep one); the repeated "Not available yet" on the dashboard; Median response time and "Interested leads answered";
checklists that stay after completion and the "Hide this checklist" button; the local-model "Ask the local assistant" box inside Settings; Clear all on a
running sequence; the duplicate `follow` / `follow_profile` step types; the second LinkedIn connection concept (OAuth) on the publishing overview.

## D. Priority order for fixes

1. Confirm-before-send on Resume, Retry, Add to campaign and first launch (L1 to L5): the main safety gap found.
2. Honest counts: queued is not sent (U1, U2, U3); failures visible (U5, U6); the audit log shows recipient and text.
3. Inbox reads independent of outreach limits (U4, U15) so replies are seen.
4. Launch hygiene: removed leads stop, no duplicate people across campaigns by default, one default schedule (L9 to L13).
5. Screen clean-up (U7 to U14, U16 to U18) and the clutter list.

None of Part 2 is fixed yet. Part 1 lists the five fixes already made.

## Status after the second fix pass (21 Nov 2026, evening)

Fixed, each with a test: L1 to L5 (confirm before send, committed earlier); L9 (an untouched draft is reused instead of creating a new one on every visit);
L10 (default time zone is the sender's); L11 (a person taken off the list is stopped, also when their action is already queued); U1, U2 (queued is shown
as "waiting", not as sent; the dashboard line counts what really went out); U3 (account Accepted % and Replied % come from real sends; people who were
already connections are neither invited nor accepted); U5 (audit log: names the person and the text, says "nothing was sent", plain words for errors, a
"Messages and invitations" filter that is now the default); U7 (plain wording on the dashboard); U11 (the disabled "Manage plan" button is gone).

Still open: L6 to L8 (not changed), L12 (default exclusions: a behaviour change for the owner to decide), L13, U4 (inbox reads are spread over the day now,
but the day's reads already used cannot be given back), U6, U8, U9, U10, U12 to U18, the clutter list. Reply % on an account now means "of the people Synex sent
something to", not "of the people who accepted".
