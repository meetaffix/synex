# OutFlo vs Synex, screen comparison (Phase 1 result, 19 Nov 2026)

OutFlo screens: `docs/reference/outflo-screens/` (73 files), notes: `outflo-live-inspection-2026-11-19.md`.
Synex screens: `docs/reference/synex-screens/` (175 files = 88 states x light/dark, 1280 px wide, full-page, from the project's mocked-API harness `frontend/tests/screens.spec.ts`; no real data).
Verdicts: **match** (same content and flow), **different** (exists, but shaped differently), **missing** (OutFlo has it, Synex does not), **extra** (Synex only; candidate to remove unless it is one of our agreed extras).
Based on the screens I opened side by side (accounts list, account limits, add-leads dialog, smart sequence, review step, others hub); other Synex rows come from the screen list and routes, and are marked (not viewed) where I did not open the image.

## Cross-cutting
| Item | OutFlo | Synex | Verdict |
|---|---|---|---|
| Left rail | Dashboard, Unibox, Campaigns, Accounts, Others, What's new, Rewards, Support/Founder/Slack, user chip | Dashboard, Inbox, Campaigns, Sender accounts, Leads, Templates, Others, Settings, Help, user chip, search box (Ctrl K), org switcher, Assistant button | different (Leads, Templates, Settings, Assistant, search are extra; What's new, Rewards missing) |
| Trial/upgrade banner | yes | none (billing out of scope) | extra-not-needed; skip |
| Settings area | left menu: Profile, Billing, Integration, Notifications, Workspaces, Users, Support | one `/settings` page + `/settings/integrations` tabs + `/settings/safety` | different |
| Themes | light only | light + dark | extra (keep) |
| Toasts | green "Success" bottom-left | (not viewed) | check |

## Area 3: LinkedIn accounts
| Screen | OutFlo | Synex | Verdict |
|---|---|---|---|
| Page title / action | "LinkedIn Accounts" + "+ Connect account" | "Sender accounts" + "Connect LinkedIn account" | different (names) |
| Organization overview | Plan, Seats available, Credits granted, Credits remaining, Manage plan, View credits | Plan "Free (placeholder)", Seats, last-24h usage, View usage, Manage plan (disabled) | different (no credits) |
| Accounts list | TABLE: account, status filter, usage 24 h chips, performance chips, chevron, "Showing 1-1", Previous/Next | CARDS with health, actions today bar, request/message counters, proxy, last check, status text, Check now/Edit/Manage/Reconnect, search + status select | different (cards vs table; Synex has extra info) |
| Empty state | "Let's Get You Started" + connect button + 3 ticks | `sender-empty` (not viewed) | check |
| Connect drawer, 3 choices | right drawer: Extension (Recommended), Credentials, Share link | modal `connect-form` with options and live progress states (starting, code rejected, approval, manual, failed, succeeded) | different (Synex has no Extension path yet and no share-link card; has richer progress states) |
| Credentials form | org email chip, email/phone, password, Sync Preferences (2 radio cards), Connect, Set Proxy Configuration (URL, protocol, host, port, user, pass, Test) | form with test connection, own-proxy field (not viewed in detail) | check |
| Account header | banner, SSI box, avatar, headline, Resync, location, company, badges, "connected by ... since" | name, headline, avatar, "Connected since", active campaigns, last check, proxy, Resync | different (no banner/SSI/location/company) |
| Tabs | Sender Limits, Inbox Privacy, Health, Account, Manage Connections, AI Configuration | Sender limits, Inbox privacy, Health, Manage connections, AI configuration, Account | match (order differs: Account last) |
| Sender limits | recommendation banner, Smart Auto-Increase 4 buttons, Range +-1..10, 10 metric rows with per-row switch and expand | recommendation banner, test-account profile, 24 h usage table, auto-increase 5 radio cards, daily variation, 13-row table (all inputs visible) | different (Synex shows more actions and our hard maxima; no per-row expand; "Range" is "Daily variation") |
| Default limits | 25/25/30/25 with max 40 | new accounts start at 0, max 40/100/80 (agreed safety rule) | different on purpose (safety rule wins) |
| Inbox privacy | Full inbox sync card, access-required notice, share link | `account-privacy`, `account-privacy-locked` | match (not viewed in detail) |
| Health | one switch: auto-withdraw stale invites | Health tab (not viewed) | check |
| Account tab | Deactivate seat, Delete account | `account-lifecycle`, disconnect confirm, edit account, reconnect link | different (Synex richer) |
| Manage connections | notice, Export/Upload CSV, search, list | `account-connections` | check |
| AI configuration | Assigned voice + Assign voice (7 voices, Clone My Voice) | `account-ai` | check |
| Resync / refresh icon, LinkedIn icon | yes | Resync only | missing (icons) |

## Area 4: Leads
| Screen | OutFlo | Synex | Verdict |
|---|---|---|---|
| Location | Others > Lead List Management (`/others/lead-management`) | Top-level Leads with tabs Contacts / Lists / Companies / Do not contact | different (placement) |
| Lead Lists tab | search, filter (All/Lead List Only/Campaign List Only), export icon, "System lists: Do Not Contact", empty "No lists found" | `leads-lists`, `leads-lists-empty` (not viewed) | check |
| Leads tab | search all leads | Contacts tab with Columns picker | match/extra |
| Create lead list | name dialog + Next | (not viewed) | check |
| Do Not Contact | Contacts + Companies tabs, Import CSV, Export, Add profiles, search, table | tab "Do not contact" + Companies tab | match (not viewed) |
| Campaign source list (10) | profile, CSV, my list, basic search, Sales Nav leads, Recruiter, Post, Event, Companies, Sales Nav Accounts | 8 cards: Paste profile links, CSV or Google Sheets, existing lists, basic search, post reactions/comments, event attendees, Sales Navigator leads, companies; group members "coming soon" | different: Recruiter and Sales Nav Accounts missing; Google Sheets, group members extra; every card says "estimate and preview before anything is added" (extra, agreed) |
| Source forms | URL, account select, list name, limit (max 1,000 / 2,500), scrape type for posts | estimate + preview flow (not viewed) | different (agreed beat-OutFlo extras) |
| Campaign variables on a lead | "Campaign variables / + New variable" | (not found) | missing |

## Area 5: Campaigns and AI writing
| Screen | OutFlo | Synex | Verdict |
|---|---|---|---|
| List | table: name, status, leads, accepted %, reply %, accounts, trash; empty "Ready to start..." | `campaigns-table`, `campaigns-empty` | match (not viewed) |
| Create | name dialog, immediately creates a draft and opens the wizard | `/campaigns/new` page | different |
| Wizard header | back, editable name, AI Campaign Context, Save draft; 4 steps (circles + line) | back, name field, Saved/Unsaved text, Save draft, AI campaign context; 4 pill steps | match (styling differs) |
| Step 1 senders | table with checkbox, "up to 25 (rolling 24h)", View limits, allocation icon | `campaign-builder-senders` (not viewed) | check |
| Action Allocation drawer (reserve daily slice, 4 switches) | yes | none found | missing |
| Step 2 leads | empty state + Add Leads + Next | `campaign-builder-leads` | check |
| Step 3 Classic | vertical blocks, If Connected chip, Wait, Message 1, variables menu, AI agent switch | blocks with Insert variable, Insert template, Add spintax, custom variable, Preview, "Synex AI writing" switch, validation text | match (more controls in Synex) |
| Step 3 Smart | **n8n-like canvas**: Campaign Start node, + Add Action, node menu (9 actions + 2 conditionals), right drawers per node, branches, zoom/fit, Collapse, Templates, validate, clear | a VERTICAL STACK of cards (Send connection request, Wait, Send message, End, If connection with Connected / Not connected boxes), zoom %, Full screen, Clear all, Templates | **different: not a node canvas**. Rebuild with React Flow |
| Node types | Send Connection Request, Send Message, Send Voice Note, Follow Profile, Like a Post, View Profile, Send Free InMail, Send InMail, Withdraw Invite, If Connection, Is Active on LinkedIn | connection request, wait, message, end, if connection (others not seen) | missing most node types (to confirm in code) |
| Workflow Templates | 4 templates + Previous Campaigns tab, graph preview | "Templates" button (not viewed) | check |
| Sequence gear: Configure webhook | yes | none | missing |
| AI message drawer | Direct/AI assisted, per-profile/per-sender reads, tone, strategy, instructions | `campaign-builder-ai-drawer` | check |
| AI Campaign Context | Upload / Context / Guardrails, website context, import template chips | `campaign-builder-context` | check |
| Step 4 review | schedule (Sun first), exclusions, lead list, senders, sequence, confirm, Launch | schedule (Mon first), exclusions (6 toggles), lead list, senders, sequence, launch checklist, dry run, confirm, "Fix 1 thing to launch" | different, Synex richer (agreed extras: checklist, dry run) |
| Timezone | select of 25 abbreviations | text field "UTC" | different |
| Campaign detail / stats page | not seen (nothing launched) | none seen | unknown |

## Area 6: Inbox
| Screen | OutFlo | Synex | Verdict |
|---|---|---|---|
| Layout | list + thread + profile panel; account chips, "+ Add", search, date presets, filter, "..." Export CSV | `inbox-empty`, `inbox-thread`, `inbox-filters-and-bulk` (not viewed) | check |
| Filters | Needs My Reply, I Messaged Last, Status (Starred, Drafts, Scheduled, Unread), Tags, System tag, Archived, sender accounts, include/exclude campaigns + messages sent/responses | Filters + bulk actions toolbar | check |
| Empty states | "No conversations yet" + "Your inbox is quiet" | exists | check |
| Interest labels, AI suggested replies | none | agreed extras | extra |

## Area 7: Dashboard
| Screen | OutFlo | Synex | Verdict |
|---|---|---|---|
| Cards | 3 performance + 3 interested/response cards, date, campaign, account filters, Customize cards, Share, download | `dashboard-rich`, `-live-feeds`, `-first-run`, `-campaign-totals` | check (not viewed) |
| Performance overview chart | Weekly/Daily, 7 toggle chips | funnel (`dashboard-funnel.spec`) | check |
| Per-sender table | yes | (not seen) | check |

## Area 8: AI assistant, Area 9: Templates
| Item | OutFlo | Synex | Verdict |
|---|---|---|---|
| Voice/text assistant | none | Assistant button + settings (extra) | extra (agreed in the brief) |
| Templates page / saved replies | none (only Workflow Templates and AI context chips) | `/templates` (list, empty) | extra (agreed in the brief) |

## Area 10: Settings and integrations
| Screen | OutFlo | Synex | Verdict |
|---|---|---|---|
| Profile | email, name, phone, company, designation, password | `settings` (profile + assistant + local assistant cards) | different |
| Billing, Credits | plans, credit rate card | "placeholder", disabled | out of scope |
| Integrations | MCP, Slack, Webhook, API, HubSpot, Smartlead, Instantly, HeyReach migration | tabs: notifications, webhooks, API, email, usage, support (+ MCP/Slack/HubSpot/migration not confirmed) | different |
| Notifications | emails list + Account Connected / Disconnected / Any Message + Campaign related | tab `integrations-notifications` | check |
| Support | contact form + founder call | tab support | different |
| Social engagement | Posts board (5 columns) / Calendar, Engagement, Reviewers | Others > Content publishing (Studio, Calendar, Queue, Activity, Engagement, Analytics, Connections) | different (Synex bigger) |
| Rewards, What's new | pages | none | missing (low value) |
| Others hub cards | Lead List Management, LinkedIn Social Engagement | one card, Content publishing | different (lead lists should be reachable from Others) |

## Area 11: Safety / Area 12: Design
| Item | OutFlo | Synex | Verdict |
|---|---|---|---|
| Safety page, kill switch, ceilings | none | `/settings/safety`, admin | extra (agreed) |
| Visual language | indigo rail + purple, light only | teal-green, soft, dark mode | different (brand choice; not copied) |
| Typography | Inter-like | Plus Jakarta Sans | different |

## What the screens say about priorities
1. Smart sequence: Synex is a stacked list, not a canvas. Biggest gap, and you asked for React Flow.
2. Missing node types and the Configure-webhook gear in the sequence.
3. Campaign: "Action Allocation" drawer, campaign variables on leads, timezone select.
4. Leads: Recruiter and Sales Navigator Accounts sources; lead lists placed under Others as in OutFlo (or both).
5. Accounts: table list option, banner/SSI/location in the header, extension and share-link connect paths, Resync/refresh icons.
6. Shell: What's new and Rewards pages; Settings left menu.
7. Items marked "check" need a closer side-by-side once you say GO (I did not open every Synex image).

## Decisions I need from you at GO
- Accounts list: switch to the OutFlo table, or keep cards and add the table as a view?
- Where lead lists live: move under Others like OutFlo, or keep top-level Leads and add the Others card?
- Colours: keep Synex teal and soft look (my default) or restyle toward OutFlo's indigo? Brief says Synex keeps its design.
- Safety defaults stay at 0 for new accounts and our ceilings (not OutFlo's 25/30 defaults).

## Corrections after auditing the code in Phase 2 (19 Nov 2026)
- Recruiter and Sales Navigator Accounts lead sources: NOT missing. Backend (`lead_sources.py`) and the add-leads dialog have them; the screenshot harness only mocks a shorter list.
- Smart sequence node types: all 11 OutFlo types exist in the model. Only the view was a list; it is now a React Flow canvas (built).
- Action Allocation drawer: exists ("Reserve actions for this campaign", covered by `campaign-builder.spec.ts`).
- Timezone: Synex has a searchable field with every IANA zone (a superset of OutFlo's 25-abbreviation select). Kept.
- What's new: exists (`components/shell/WhatsNew.tsx`). Rewards: still missing.
- Built since: Smart canvas, strict step unlocking with ticks and locks, accounts table view (cards stay as a second view and as the narrow-screen view), Lead List Management card on Others.
- Still open: sequence "Configure webhook" gear (per-campaign webhook needs a backend field), per-lead campaign variables on "Add LinkedIn profile", Rewards page, extension connect path, account header (banner, location, company), Settings left menu.
- Test notes: `app-shell.spec.ts` listed the publishing tabs without "Engagement" (stale before my work; fixed). `sender-accounts.spec.ts` "the sign-in shows the time elapsed..." fails (a refresh sends a DELETE to the connect attempt); not caused by the accounts table, not yet investigated.
