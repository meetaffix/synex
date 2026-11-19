# Synex build checklist (definition of done)

Source: `docs/reference/outflo-inspection-2026-11-16.txt` (section numbers in brackets), its gap list (G1 to G10), and Synex extras (X).
Rule: tick `[x]` only with evidence in the line (test name or screenshot path). `[~]` means built but not fully verified (reason given). `[ ]` means not done.
Tags: `[LV:mock]` = LinkedIn-dependent, built and tested on the mock site only; `[LV:real]` = verified on real LinkedIn (none yet). `tools/checklist_status.py` counts them. "Done" for an area means every line is ticked.
"Unverified LV" = built and tested on the mock site; not verified on real LinkedIn (no access or no GO yet).
Written 2026-11-16. Counts per area are at the end of this file.

## Area 3: LinkedIn accounts [4, 2.3, 6.2, G5, G9]

### 3.A Accounts list and overview
- [x] 3.A01 Organization overview card: plan name, trial end, seats used of included, seats available [4.1] (accounts-list.spec 'overview card')
- [x] 3.A02 Seats used / available endpoint `/linkedin-accounts/overview` (backend `account_management.py`, mock in tests)
- [x] 3.A03 Usage meter on the card (last 24 hours), "View usage" link, "Manage plan" disabled and marked Coming soon (no billing yet) [4.1] (accounts-list.spec 'overview card')
- [x] 3.A04 Account row: avatar, name, active campaigns count, status badge [4.2] (sender-accounts.spec.ts)
- [x] 3.A05 Account row: globe/proxy indicator (row shows Proxy Set/None (sender-accounts.spec))
- [x] 3.A06 Account row: 24-hour usage per action with today's range (connections, messages) [4.2] (accounts-list.spec '24-hour usage'; test_account_overview)
- [x] 3.A07 Account row: "Smart" pill when auto-increase is on [4.2] (accounts-list.spec '24-hour usage')
- [x] 3.A08 Account row: performance chips, accepted % and reply % [4.2] (test_account_overview; accounts-list.spec)
- [x] 3.A09 Status filter: All, Active, Needs attention [4.2] (accounts-list.spec 'filter')
- [x] 3.A10 Name search [4.2] (accounts-list.spec 'filter')
- [x] 3.A11 Pagination Previous/Next [4.2] (accounts-list.spec 'paged')
- [x] 3.A12 "Manage" link from each row to the account page (account-management.spec.ts #1)
- [x] 3.A13 Empty state with "Connect account" call to action (sender-accounts.spec 'empty state'; accounts-list.spec 'no accounts')
- [x] 3.A14 Loading and error states for the list (sender-accounts.spec 'a failed list load shows a retry')

### 3.B Connect account
- [~] 3.B01 Connect with credentials (owner types password and code; live state machine; real LinkedIn verified 2026-11-15)
- [x] 3.B02 Drawer "Add LinkedIn account" with the three methods [4.3] (ConnectDialog; accounts-list.spec 'connect dialog' (credentials form plus other ways))
- [x] 3.B03 Method: Connect via extension, shown as "Coming soon" (extension comes later; disabled, not inert) (accounts-list.spec 'connect dialog' (disabled, Coming soon))
- [x] 3.B04 Method: Share connection link, with Copy and instructions [4.3] (test_account_delete InviteLinkTest; accounts-list.spec 'connect dialog')
- [x] 3.B05 Reconnect link for another person (existing; sender-accounts.spec.ts)
- [x] 3.B06 Elapsed time, refresh-resume of an in-progress connect (only the attempt id is kept, never the password), "Connect another" (sender-accounts.spec 'time elapsed and a page refresh resumes it')
- [x] 3.B07 "Already installed? Refresh" replaced by honest text: the extension button is disabled with "Coming soon. Nothing to install today." (accounts-list.spec 'Chrome extension')

### 3.C Account page
- [x] 3.C01 Page at `/linkedin-accounts/:id` with header, status badge and summary (account-management.spec.ts #1)
- [x] 3.C02 [LV:mock] Resync button (runs the account check)
- [x] 3.C03 Six tabs: Sender limits, Inbox privacy, Health, Manage connections, Account (+ AI configuration, see 3.H); tab in the address, arrow-key navigation (account-management.spec.ts #1)
- [x] 3.C04 Unknown account shows a clear message and a way back (account-management.spec.ts #9)
- [x] 3.C05 Banner: profile photo, headline, location, company, "connected since" line [4.4] (account-management.spec #1 (Connected since, profile link))
- [x] 3.C06 SSI score banner: shown only from real collected data, otherwise an honest "no data" (page says so now) [4.4] (account-management.spec #7 (honest no data))
- [x] 3.C07 Per-account activity list (recent tasks and results) (account-management.spec #7 (Recent activity in Health tab))

### 3.D Sender limits [4.6]
- [x] 3.D01 Recommended-limits banner: Apply limits, Keep current, Show suggestions (account-management.spec.ts #2)
- [x] 3.D02 Suggestions never exceed hard ceilings (account-management.spec.ts #2)
- [x] 3.D03 24-hour usage table per action with range and hard maximum (account-management.spec.ts #3)
- [x] 3.D04 Presets: Conservative (+1/week), Balanced (+2/3 days), Aggressive (+3/day), Custom, Fixed (account-management.spec.ts #4)
- [x] 3.D05 Range selector plus or minus 1 to 10 (account-management.spec.ts #4)
- [x] 3.D06 Per-action table: daily limit, increase by, every N days, stop at, dynamic (account-management.spec.ts #4)
- [x] 3.D07 Values cannot exceed the hard maximum; limit never above stop value (account-management.spec.ts #4)
- [x] 3.D08 Unsaved-changes notice, Save, Discard (account-management.spec.ts #4)
- [x] 3.D09 Refused save keeps what was typed (account-management.spec.ts #5)
- [x] 3.D10 Actions listed: profile views, connection requests, messages, follows, connection checks, inbox reads, connections reader, lead collection, invitation withdrawals, post likes, InMails, voice notes (account-management.spec limits table, 13 rows)
- [x] 3.D11 Server-side: a policy above a ceiling is refused (test_safety_area 'a policy above any ceiling is refused'; test_account_policy)

### 3.E Inbox privacy [4.7]
- [x] 3.E01 Which conversations Synex reads (all / only campaign) (account-management.spec.ts #6)
- [x] 3.E02 Inbox history days (account-management.spec.ts #6)
- [x] 3.E03 Owner-only lock with "Account access required" note (account-management.spec.ts #6)
- [x] 3.E04 "Share with account owner" link with Copy (account-management.spec 'send the owner a link')

### 3.F Health [4.8]
- [x] 3.F01 [LV:mock] Auto-withdraw stale invites: setting saved and executed by the engine sweep (backend/tests/test_withdraw.py; account-management.spec health test). Unverified on real LinkedIn
- [x] 3.F02 Honest SSI message (account-management.spec.ts #7)
- [x] 3.F03 Health summary: last check, last warning, paused reason, restrictions (account-management.spec #7 (Health summary))

### 3.G Account tab and Manage connections [4.9, 4.10]
- [x] 3.G01 Deactivate seat with confirmation, frees seat, keeps history (account-management.spec.ts #8)
- [x] 3.G02 Disconnect with confirmation (SettingsTabs; sender-accounts.spec.ts)
- [x] 3.G03 Delete account (permanent) distinct from disconnect, with typed confirmation (test_account_delete; account-management.spec 'delete needs the exact name')
- [x] 3.G04 Connections subtab: list, search, paging (account-management.spec.ts "manage connections: lists...")
- [x] 3.G05 Invitations subtab (same test)
- [x] 3.G06 Reload with status, queued/running, one at a time (account-management.spec.ts "reload queues one"; backend test_account_connections ReloadTest)
- [x] 3.G07 "Syncs gradually" notice (same test)
- [x] 3.G08 Export CSV, formulas neutralised (backend ExportImportTest; UI test "CSV is uploaded...")
- [x] 3.G09 Upload CSV with result counts (same)
- [x] 3.G10 Empty state with how to fill the list (account-management.spec.ts "empty list")
- [~] 3.G11 [LV:mock] Real reads of connections and invitations: Unverified LV (selectors fixture-tested only)

### 3.H AI configuration [4.11]
- [x] 3.H01 Tab "AI configuration" with assigned voice (none by default) (account-management.spec 'AI configuration')
- [x] 3.H02 "Assign voice" dialog with preset voices and a play sample (account-management.spec 'AI configuration')
- [x] 3.H03 Preset voices from an open-source, commercially licensed TTS (licence recorded) (test_voices (licences); samples disabled until Piper installed)
- [~] 3.H04 "Clone my voice" dialog: name, record or upload .m4a/.mp3/.wav, 30 to 60 s, ownership confirmation, Create (clone is disabled with the reason: no commercially licensed cloning model verified)
- [x] 3.H05 Voice cloning only with a commercially licensed open model, else disabled "Coming soon" with reason (account-management.spec 'AI configuration' (disabled with reason))

### 3.I Quality for area 3
- [x] 3.I01 Axe and 360 px checks on account screens, both themes (a11y.spec.ts, responsive-360.spec.ts, `-g account-`: 14 pass)
- [~] 3.I02 Screens viewed at 360, 768, 1280 in both themes after final change (captured in docs/reports/screens/area-3/; I looked at two of them)
- [x] 3.I03 Keyboard walk-through of the account page recorded as a test (account-management.spec 'keyboard only')
- [x] 3.I04 Playwright against `vite preview` production build (full run 2026-11-16: 408 passed, 0 failed, 84 screenshot specs skipped by design)

## Area 4: Leads [5, 6.1, G7, X]

### 4.A Source picker
- [x] 4.A01 "How would you like to add leads?" dialog with ordered sources (existing; verify against the report) (add-leads.spec 'every source is listed')
- [x] 4.A02 Unavailable sources show a reason, not hidden (add-leads.spec 'every source is listed' (reason text shown); test_lead_sources_more group)
- [x] 4.A03 Estimate shown before every import (pages, minutes, limit cost) [X] (add-leads.spec 'an event' (server estimate); test_lead_sources_more estimate)
- [x] 4.A04 Preview of the first results before saving [X] (preview before import: test_lead_collections 'pasted links preview import and skip options')

### 4.B The twelve sources
- [x] 4.B01 Add one LinkedIn profile: URL, optional name (leads 'Add lead' form and 'Paste profile links' source; leads-extras.spec)
- [x] 4.B02 Profile: custom campaign variables (name, value per person, Create variable) [5.1] (leads-extras.spec 'custom campaign variables'; test_lead_variables)
- [x] 4.B03 Profile: "Campaign exclusions apply" notice (leads-extras.spec 'custom campaign variables' (notice in the Add lead form))
- [x] 4.B04 Upload CSV: drag and drop, Browse, 5 MB maximum (add-leads.spec 'CSV source ... over 5 MB')
- [x] 4.B05 CSV: required "LinkedIn URL" column, Download sample CSV (add-leads.spec 'sample file'; test_lead_collections 'csv asks for the columns')
- [x] 4.B06 CSV: column mapping step and preview [X] (test_lead_collections 'csv asks for the columns then imports')
- [x] 4.B07 CSV: counts of rows read, valid, without a LinkedIn link, repeated in the file; already-known people are counted as skipped at import (test_lead_collections 'csv asks for the columns then imports')
- [x] 4.B08 Add from my saved list: list picker, Refresh, Create empty list (lists source in AddLeadsDialog; test_lead_collections)
- [x] 4.B09 Saved lists empty state "No saved lead lists found" (AddLeadsDialog shows 'You have no lists yet.')
- [~] 4.B10 [LV:mock] Basic LinkedIn search URL: URL, account, list name (dated default), limit (default 100, max 1,000) (collection framework exists; Unverified LV) (test_lead_collections search; Unverified LV)
- [~] 4.B11 [LV:mock] Sales Navigator leads: URL, account, list, limit max 2,500 (Unverified LV: no access) (test_lead_sources_more CollectorTest seats; Unverified LV: no access)
- [~] 4.B12 [LV:mock] Recruiter: URL, recruiter account, list, limit max 2,500 (Unverified LV: no access) (test_lead_sources_more CollectorTest seats (same reader); Unverified LV: no access)
- [~] 4.B13 [LV:mock] LinkedIn post: URL formats (activity, ugcPost, share), scrape type Reactions / Comments / Both, limit 1,000 (post address validation in test_lead_sources_more; reader exists; Unverified LV)
- [~] 4.B14 [LV:mock] LinkedIn event: URL, "account must be attending" warning, limit 1,000 (test_lead_sources_more event collector; add-leads.spec warning; Unverified LV)
- [~] 4.B15 [LV:mock] LinkedIn companies: company list source (opens its own form, not a redirect) (test_lead_sources_more company collector and company lists; leads-extras.spec; Unverified LV)
- [~] 4.B16 [LV:mock] Sales Navigator accounts: company search URL, account, list, companies limit 100 (Unverified LV) (test_lead_sources_more company collector; Unverified LV: no access)
- [x] 4.B17 LinkedIn group: disabled "Coming soon" until built (add-leads.spec 'unbuilt one says Coming soon'; test_lead_sources_more group)
- [x] 4.B18 [LV:mock] Extra: my connections (from the connections reader) (connections source: test_lead_collections / account connections reader)
- [~] 4.B19 [LV:mock] Extra: engagers of my own posts (test_lead_sources_more own posts collector; Unverified LV)
- [x] 4.B20 Extra: inbox contacts (inbox source: test_lead_collections)
- [x] 4.B21 Extra: Google Sheets (open-source/CSV-export path; no paid service) (csv source with Google Sheets link: test_lead_collections sheet link test)
- [x] 4.B22 Extra: bulk paste of links (urls source: test_lead_collections 'pasted links preview import')
- [x] 4.B23 Extra: degree filter (1st, 2nd, 3rd) (test_lead_collections 'degree filter and per-degree counts')
- [x] 4.B24 Extra: dedupe within list and against other lists (stage() drops duplicates; test_lead_collections skip options)
- [x] 4.B25 Each source has a tooltip on every field [5.12] (a hint line per source in AddLeadsDialog (add-leads.spec))
- [x] 4.B26 Each source checks the account's collect_leads ceiling and shows what remains (add-leads.spec 'page reads left today'; test_lead_sources_more estimate)
- [x] 4.B27 URL validation messages per source (wrong host, wrong type, missing) (test_lead_sources_more 'each source names what is wrong with its address')

### 4.C Lead lists and leads table
- [x] 4.C01 Lead Lists tab: create list, search, filter (all, with leads, empty), sort, export CSV (lead-lists.spec; test_lead_list_export)
- [x] 4.C02 List detail: leads open from the list, count, delete with a confirmation that says the leads stay (lead-lists.spec 'deleting a list')
- [~] 4.C03 Leads tab: table with search, filters, bulk select, bulk actions, export CSV (LeadsPage has search, status and list filters, select all, bulk status, bulk delete, Export; only leads-columns.spec covers it)
- [x] 4.C04 Lead detail: fields, variables, campaigns it is in, status history (leads-extras.spec 'a lead's details show its campaigns and history'; test_lead_overview)
- [x] 4.C05 Add lead to a campaign from the table (leads-extras.spec (add to a campaign); test_lead_overview adds to draft and active campaigns)
- [x] 4.C06 Lead "Lead not present in any campaign" state (leads-extras.spec 'Lead not present in any campaign'; test_lead_overview)
- [x] 4.C07 Empty, loading, error states (lead-lists.spec 'no lists ... failed load shows a retry'; leads-empty a11y state)

### 4.D Do not contact [6.1]
- [x] 4.D01 System list "Do not contact" that cannot be deleted (no route deletes the list itself; test_do_not_contact ApiTest)
- [x] 4.D02 People tab: table Profile, Source, Added, Action (do-not-contact.spec 'profiles are added')
- [x] 4.D03 Companies tab (do-not-contact.spec 'companies are a separate list')
- [x] 4.D04 Add profiles: one URL per line, duplicates ignored (test_do_not_contact ApiTest add and dedupe)
- [x] 4.D05 Import CSV with `linkedin_url` column (test_do_not_contact import; do-not-contact.spec import)
- [x] 4.D06 Export CSV (test_do_not_contact export; do-not-contact.spec export)
- [x] 4.D07 Search (test_do_not_contact search; do-not-contact.spec search)
- [x] 4.D08 Remove entry with confirm (do-not-contact.spec remove asks first; test_do_not_contact)
- [x] 4.D09 Enforced at send time (test: a listed person never receives an action) (test_do_not_contact EnforcementTest (launch and precheck))
- [x] 4.D10 Company entries match leads by company (test) (test_do_not_contact company matching and enforcement)

### 4.E Quality for area 4
- [x] 4.E01 Backend tests per source (mock site) (test_lead_sources_more, test_lead_collections, test_do_not_contact, test_lead_variables)
- [~] 4.E02 Axe, 360/768/1280, both themes for every area-4 screen (axe and 360 px for leads, leads-companies, leads-do-not-contact, leads-add-sources, leads-add-event-form (all pass); screens saved in docs/reports/screens/area-4/ and two viewed)
- [x] 4.E03 Keyboard path through the lists page and its menus (lead-lists.spec 'keyboard')

## Area 5: Campaigns and AI writing [1, 2, 7, G1 to G6]

### 5.A Campaigns list [2.1]
- [x] 5.A01 List with name search (existing) (campaigns-list.spec 'search narrows the list')
- [x] 5.A02 Columns: Name, Status, Leads, Accepted %, Reply %, Accounts, Actions (campaigns-list.spec 'report's columns')
- [x] 5.A03 Status filter: Draft, Paused, Queued, Running, No more pending actions, Finished, Failed (campaigns-list.spec 'every status'; test_campaign_list StatusTest)
- [x] 5.A04 Accounts filter (campaigns-list.spec 'accounts narrow the list')
- [x] 5.A05 Row menu: Duplicate, Share sequence, Delete, Archive (disabled for a draft) (campaigns-list.spec row menu tests (4); test_campaign_list RowActionsTest)
- [x] 5.A06 Delete confirmation text (campaigns-list.spec 'delete asks first')
- [x] 5.A07 Empty state "Ready to start your first campaign?" with button (campaigns-list.spec 'empty list invites')

### 5.B Builder shell [2.2]
- [x] 5.B01 Editable campaign name in the header (campaign-builder.spec 'saves as you go')
- [x] 5.B02 Save draft (disabled until changed) (campaign-builder.spec 'saves as you go' (Save draft waits for a change))
- [x] 5.B03 Autosave with "Saving" and "Saved" indicator (campaign-builder.spec 'saves as you go' (Saving, Saved))
- [x] 5.B04 Four steps: Senders, Leads, Sequence, Review and launch (campaign-builder.spec 'four steps')
- [x] 5.B05 Builder opens with no senders and no leads [beat OutFlo] (campaign-builder.spec 'opens with no sender and no leads')
- [x] 5.B06 "Discard unsaved changes?" prompt: Discard, Save (campaign-builder.spec 'leaving with unsaved changes asks first')
- [x] 5.B07 AI campaign context button in the header (campaign-builder.spec 'AI campaign context')

### 5.C Step 1 senders [2.3]
- [x] 5.C01 Table: select all, name, limit "up to N (rolling 24h)", status badge (campaign-builder.spec 'choosing a sender')
- [~] 5.C02 Tooltip explaining splitting leads across accounts (explanatory paragraph shown instead of a tooltip)
- [x] 5.C03 Footer: accounts selected, total daily limit (campaign-builder.spec 'choosing a sender' (total daily limit))
- [x] 5.C04 "View limits" link to the account page (campaign-builder.spec 'choosing a sender' (View limits link))
- [x] 5.C05 Campaign action allocation drawer: per-action daily slice, Save, Close, explainer (campaign-builder.spec 'allocation drawer')
- [x] 5.C06 No sender: Next disabled, with the reason shown (by design Next is allowed with no sender; the launch checklist names it (test_launch_check blank campaign; builder spec 'opens with no sender'))
- [x] 5.C07 Allocation enforced by the scheduler (test) (test_campaign_settings AllocationTest (type_room obeys the reserved slice))

### 5.D Step 2 leads [2.5]
- [x] 5.D01 Empty state with Add leads (LeadsStep 'Add leads to begin'; builder spec 'move on freely')
- [x] 5.D02 Next with no leads allowed; launch checklist blocks it [beat OutFlo] (campaign-builder.spec 'move on freely'; test_launch_check)
- [x] 5.D03 Lead list chosen or created from any source (area 4) (LeadsStep list picker and Add leads (areas 4 tests))

### 5.E Step 3 sequence, Classic [2.7]
- [x] 5.E01 First block: view profile and send connection request (campaign-builder.spec 'the sequence')
- [x] 5.E02 Connection note: Direct or AI assisted, 200 character limit, warning about personalised notes (campaign-builder.spec 'the sequence' (200 characters, AI switch); AI drawer test)
- [x] 5.E03 "If connected" chip with settings (campaign-builder.spec 'the sequence' (If connected))
- [x] 5.E04 Wait blocks: first message after 1 day (minimum 180 minutes) (campaign-builder.spec 'the sequence' (at least 3 hours after acceptance))
- [x] 5.E05 Follow-up: wait in minutes, hours or days, minimum 15 minutes, "If not replied" chip (campaign-builder.spec 'minutes with a floor of 15'; test_graph MinutesWaitTest)
- [x] 5.E06 Add follow-up message, remove, reorder (campaign-builder.spec 'moved up and down')
- [x] 5.E07 Message editor with variable chips (campaign-builder.spec 'the sequence' (variable chips))
- [x] 5.E08 Settings visible on every node [beat OutFlo] (every block in the classic sequence shows its settings (builder spec 'the sequence'))
- [x] 5.E09 Empty message validation message (test_launch_check empty message; builder spec 'review ... checklist')

### 5.F Smart builder [2.7]
- [x] 5.F01 Graph canvas: Campaign start, Add action, zoom, full screen, clear all with confirmation (campaign-smart.spec 'zoom, full screen and clear all')
- [x] 5.F02 Classic | Smart switch with confirm "Switch to Smart?"; back to Classic names what it removes (campaign-smart.spec)
- [x] 5.F03 Node: Send connection request (max one; brings an If connection step with Connected and Not connected branches; 15-day wait, 1 to 30) (campaign-smart.spec menu; test_graph BranchTest)
- [x] 5.F04 Node: Send message (campaign-smart.spec; test_graph)
- [x] 5.F05 [LV:mock] Node: Send voice note (only in the Connected branch or after a message) (campaign-smart.spec voice tests; test_new_actions WorkerFlowTest)
- [x] 5.F06 Node: Follow profile (test_graph ActionNodeTest)
- [x] 5.F07 [LV:mock] Node: Like a post (test_new_actions ActionTest and WorkerFlowTest)
- [x] 5.F08 Node: View profile (test_graph ActionNodeTest)
- [x] 5.F09 [LV:mock] Node: Send free InMail (test_new_actions 'free InMail spends none'; unverified on real LinkedIn)
- [x] 5.F10 [LV:mock] Node: Send InMail (test_new_actions; stops with a reason when no credits are left)
- [x] 5.F11 [LV:mock] Node: Withdraw invite (test_new_actions 'withdraw step inside a campaign')
- [x] 5.F12 Conditional: If connection (test_graph BranchTest; campaign-smart.spec 'If step splits')
- [x] 5.F13 Conditional: Is active on LinkedIn (counts recorded replies, messages and acceptances; LinkedIn's own signal is not read) (test_graph ActiveTest)
- [x] 5.F14 Each branch has Add action and ends when it runs out of steps (campaign-smart.spec; test_graph 'empty branch ends the run')
- [x] 5.F15 Next stays disabled while a node is not ready, with the reason (campaign-smart.spec 'Next stays off')
- [x] 5.F16 Templates dialog: Templates and Previous campaigns tabs, search, a preview outline, Apply (templates-and-sequences.spec; preview in SequenceTemplates)
- [x] 5.F17 Four bundled templates (templates-and-sequences.spec 'four bundled templates')
- [x] 5.F18 Engine runs graphs and branches; the dry run follows the same branch; share, import, duplicate keep the tree (test_graph, 19 tests)

### 5.G AI writing drawer [1, G1]
- [x] 5.G01 Toggle "Personalise with live LinkedIn data" on each message (campaign-builder.spec 'AI writing' (switch))
- [x] 5.G02 Drawer "Configure AI for message N" with Direct | AI assisted (campaign-builder.spec 'AI writing' (Direct and AI assisted tabs))
- [~] 5.G03 Direct tab: editor with Preview link (Direct tab explains; the editor has its own Preview)
- [x] 5.G04 Card linking to AI campaign context (campaign-builder.spec 'AI writing' (context card))
- [~] 5.G05 [LV:mock] Per-profile data options (role and company, recent posts, skills, career transitions, shared interests), each collected by paced tasks (current role and company work; recent posts, skills, career, interests are disabled 'coming soon' (need the paced profile reader); test_ai_writing refuses them server-side)
- [x] 5.G06 Per-sender read-only list (how the sender talks, profile, previous messages, sequence) (campaign-builder.spec 'AI writing' (per-sender list))
- [x] 5.G07 Tone: Auto, Professional, Casual, Witty, Direct (campaign-builder.spec 'AI writing' (tone); test_ai_writing prompt test)
- [x] 5.G08 Strategy: Auto, Common ground, Value offer, Curiosity hook (campaign-builder.spec 'AI writing' (strategy))
- [x] 5.G09 Generation instructions box with Insert variable buttons (campaign-builder.spec 'AI writing' (instructions and insert buttons))
- [x] 5.G10 Preview message shows cost estimate first [beat OutFlo] (campaign-builder.spec 'AI writing' (preview and its cost); test_ai_writing preview)
- [x] 5.G11 Regenerate and edit after generation (Write another in the drawer; edit after generation in the review list (campaign-builder.spec 'AI messages show their cost'))
- [x] 5.G12 Bulk generation before launch with total cost estimate and review (never during sending) (campaign-builder.spec 'AI messages show their cost'; test_launch_check)
- [x] 5.G13 Unsaved-changes prompt on closing the drawer (campaign-builder.spec 'AI writing' (Unsaved changes))
- [~] 5.G14 Provider interface: Deepgram default, local Ollama option (settings) (Deepgram, Ollama and the template provider exist (test_ai_writing OllamaTest); chosen by AI_PROVIDER, no settings screen yet (area 8 and 10))
- [ ] 5.G15 Usage meter counts generations (usage meter replaces credits)

### 5.H Variables and preview [1.9, 1.12]
- [x] 5.H01 Spintax (campaign-builder.spec 'the sequence' (Add spintax))
- [~] 5.H02 List variables with custom ones (custom variable box in the editor; per-lead values from the lead form (area 4))
- [x] 5.H03 linkedin_firstName, linkedin_lastName, linkedin_company, linkedin_jobTitle, linkedin_headline, linkedin_location (test_message_variables ApiTest)
- [x] 5.H04 sender_firstName, sender_lastName, sender_company, sender_title (test_message_variables (sender values; dry run))
- [x] 5.H05 Placeholder chips in the editor (campaign-builder.spec 'the sequence' (chips))
- [~] 5.H06 Message preview modal: sender selector, lead selector, shuffle (preview dialog built; render endpoint tested (test_message_variables); no UI test of the dialog yet)
- [~] 5.H07 Preview empty state "No data available" (built; no UI test yet)
- [~] 5.H08 Missing-variable warning per lead (warning built; test_message_variables checks the unresolved list)

### 5.I AI campaign context [1.17, G2]
- [~] 5.I01 Upload tab: .txt .md .pdf .docx up to 5 MB, autofill from files, enter manually (files .txt and .md only; PDF and Word are not read (said in the panel))
- [~] 5.I02 Add website with URL field (the address is saved; Synex does not read the site (said in the panel))
- [x] 5.I03 Context tab: goals, audience, offer, value (5,000 characters, template chips) (campaign-builder.spec 'AI campaign context' (templates))
- [x] 5.I04 Campaign meeting link overriding sender link (campaign-builder.spec 'AI campaign context')
- [x] 5.I05 Qualification questions (Context tab fields)
- [x] 5.I06 Proof points (Context tab fields)
- [x] 5.I07 Common objections and answers (Context tab fields)
- [x] 5.I08 Guardrails: Do not mention list, additional notes (5,000 characters) (campaign-builder.spec 'AI campaign context' (guardrails))
- [x] 5.I09 Save AI settings, Close (campaign-builder.spec 'AI campaign context')
- [~] 5.I10 Used by messages and by inbox suggested replies (used by AI messages now (test_ai_writing); inbox suggested replies come with area 6)

### 5.J Voice notes [1.16, G3]
- [x] 5.J01 Direct: record (as .wav) or upload .m4a/.mp3/.wav, up to 60 s and 20 MB (test_new_actions VoiceModuleTest; campaign-smart.spec upload)
- [x] 5.J02 AI assisted: script up to 1,000 characters, no variables (one recording for everyone) (test_new_actions 'script rules'; campaign-smart.spec)
- [x] 5.J03 Sender voice readiness panel (test_new_actions 'readiness'; campaign-smart.spec)
- [x] 5.J04 Language and accent: English US, UK, India (India needs a voice set by the installer: Piper has none) (campaign-smart.spec)
- [x] 5.J05 Preview voice note with its cost ($0, made locally) (campaign-smart.spec)
- [x] 5.J06 Open-source TTS: Piper (MIT), optional and not bundled; voice licences listed (docs/DEPENDENCIES.md; test_new_actions with a stand-in engine)

### 5.K Step 4 review and launch [2.8 to 2.11]
- [x] 5.K01 Schedule: timezone dropdown, per-weekday operating hours, Apply to all (campaign-builder.spec 'review: schedule'; test_campaign_settings ScheduleTest)
- [x] 5.K02 Lead list summary (review step lead list line)
- [x] 5.K03 Exclusion: Do not contact (on, locked, link) (campaign-builder.spec 'review: schedule' (locked on))
- [x] 5.K04 Exclusion: leads in other campaigns (test_campaign_settings ExclusionTest; builder spec (toggle saved))
- [x] 5.K05 Exclusion: leads already reached via other campaigns (test_campaign_settings ExclusionTest)
- [x] 5.K06 Exclusion: already reached by the same sender (test_campaign_settings ExclusionTest)
- [x] 5.K07 Exclusion: messaged by other senders (test_campaign_settings ExclusionTest)
- [x] 5.K08 Exclusion: existing connections, with explanation and link (test_campaign_settings ExclusionTest; builder spec)
- [x] 5.K09 Sender summary with Edit senders (review step senders summary)
- [~] 5.K10 Sequence summary with Preview and Edit (sequence summary with Edit sequence; no Preview message link in the summary)
- [x] 5.K11 Launch checklist: no sender, no leads, empty message, unreviewed AI drafts, missing schedule, each with its own message (test_launch_check; builder spec 'checklist names every blocker')
- [x] 5.K12 Confirmation checkbox and Launch button, labelled with the blocking reason (campaign-builder.spec 'review' (Fix 3 things to launch))
- [x] 5.K13 Dry run (no real actions, shows what would happen) (campaign-builder.spec 'dry run'; test_launch_check DryRunTest)
- [x] 5.K14 Launch respects ceilings, allocation, hours (backend tests) (launch uses the engine limits: test_outreach (89 tests) and test_campaign_settings)

### 5.L Quality for area 5
- [x] 5.L01 Backend tests for engine, graph branches, exclusions (test_graph; test_campaign_settings; test_launch_check)
- [ ] 5.L02 Flaky draft-generation test fixed and run 20 times in a row
- [~] 5.L03 Axe, 360/768/1280, both themes for every screen (axe and 360 px for every builder state and the list (pass); 768 and screenshots not yet viewed for area 5)
- [x] 5.L04 Keyboard path through the builder (campaign-smart.spec 'keyboard'; campaign-builder.spec)

## Area 6: Inbox [3, G8]
- [x] 6.01 Three-pane layout: list, thread, profile panel (existing; audit) (inbox.spec 'the list shows...'; screenshot docs/reports/screens/area-6/inbox-thread-light-1280.png)
- [x] 6.02 "Select a conversation" empty state (inbox.spec 'the list shows... nothing is selected at first')
- [x] 6.03 Header menu: Export CSV with current filters (inbox.spec 'Refresh ... Export CSV'; test_inbox ExportRefreshTest)
- [x] 6.04 Account chips and account switcher (inbox.spec 'account chips'; test_inbox FilterTest)
- [x] 6.05 Search all conversations (inbox.spec 'account chips ... search'; test_inbox 'search covers name, company and message text')
- [~] 6.06 Date presets: Today, Yesterday, Last week, Last month, Last quarter, Custom range with Apply (inbox.spec custom range fields and the seven presets are listed; test_inbox date filter; the preset-to-date arithmetic has no unit test)
- [x] 6.07 Filter: Needs my reply (inbox.spec 'filters'; test_inbox 'needs my reply')
- [x] 6.08 Filter: I messaged last (inbox.spec 'filters'; test_inbox 'i messaged last')
- [x] 6.09 Status: Starred, Drafts, Scheduled, Unread (inbox.spec 'filters'; test_inbox 'status filters')
- [x] 6.10 Tags (custom) and system tags (inbox.spec bulk tag and profile panel; test_inbox BulkTest; system tags are the five interest labels)
- [x] 6.11 Archived filter (inbox.spec 'filters' (Archived); test_inbox FilterTest)
- [x] 6.12 Sender accounts filter (inbox.spec 'account chips'; test_inbox FilterTest)
- [~] 6.13 Campaigns filter: include or exclude, all campaigns (test_inbox 'campaigns with include and exclude'; the control is built, no browser test)
- [~] 6.14 "Include conversations where": messages sent or responses (test_inbox 'include where'; the control is built, no browser test)
- [x] 6.15 Conversation card: avatar, name, unread badge, snippet, received-by chip, time (inbox.spec 'the list shows...')
- [x] 6.16 Hover star and selection checkbox (inbox.spec 'star from the row' (star and checkbox are always visible, not hover-only))
- [x] 6.17 Bulk actions: mark read, archive, tag, star (inbox.spec 'star ... bulk bar'; test_inbox BulkTest)
- [x] 6.18 Thread: header, date separators, bubbles (inbox.spec 'opening a thread ... date separators')
- [~] 6.19 Reply box: emoji, attachment, voice message, schedule, AI button, Send, sending-from account (inbox.spec reply, emoji, schedule, suggested reply, sending-from; attachment and voice message are disabled 'coming soon')
- [x] 6.20 Schedule message (inbox.spec 'scheduling'; test_inbox DraftScheduleTest (due messages go through the normal send path))
- [x] 6.21 Read-only conversation message when sending is not allowed (inbox.spec 'a conversation with no sender account is read-only')
- [x] 6.22 Sending checked against outreach limits; reading uses its own ceiling (test_inbox DraftScheduleTest (limits checked when due); refresh uses the sync_inbox ceiling, not outreach limits (ExportRefreshTest))
- [x] 6.23 AI suggested reply using campaign context, shown with cost, editable [beat OutFlo] (inbox.spec 'a suggested reply shows its cost'; test_inbox SuggestTest)
- [x] 6.24 Interest labels (interested, not interested, meeting, wrong person) [beat OutFlo] (inbox.spec 'opening a thread' (interest); test_inbox BulkTest)
- [~] 6.25 [LV:mock] Profile panel: photo, Fetch profile, followers, connections, location, local time, about, experience (stored fields shown; Fetch profile is disabled 'coming soon' (needs the paced profile reader))
- [x] 6.26 Profile panel buttons: Mark as starred, Mark as answered, Select tags, Archive (inbox.spec 'opening a thread ... profile panel')
- [x] 6.27 Lead overview with Add to campaign (inbox.spec 'opening a thread' (Lead overview); area 4 test_lead_overview)
- [~] 6.28 [LV:mock] Refresh and live sync indicator (inbox.spec 'Refresh'; the list polls every 30 s (no test of the polling))
- [~] 6.29 Axe, 360/768/1280, both themes, keyboard path (axe and 360 px pass for inbox-no-account, inbox-empty, inbox-thread, inbox-filters-and-bulk; keyboard path not a dedicated test)

## Area 7: Dashboard and analytics
- [x] 7.01 Dashboard exists (audit) (dashboard exists with summary, trend chart, account table and attention panel (app-shell.spec, states dashboard-*))
- [x] 7.02 Funnel: leads, invites, accepted, messages, replies, interested (dashboard-funnel.spec 'the funnel shows each stage'; test_dashboard_funnel)
- [x] 7.03 Acceptance and reply rate per campaign (dashboard-funnel.spec (By campaign table, 'No data' instead of 0%); test_dashboard_funnel campaign table)
- [~] 7.04 Per-account activity and limits used (per-account table with requests, accepted % and reply % exists; limits used today are on the account list (area 3), not on the dashboard)
- [x] 7.05 Date range selector (date range select; dashboard-funnel.spec 'the filters apply to the funnel too')
- [x] 7.06 Campaign and account filters (campaign and account selects; dashboard-funnel.spec)
- [~] 7.07 Charts follow the dataviz rules, both themes (trend chart and funnel bars use theme tokens; axe passes in both themes; not yet reviewed against the data-viz rules)
- [x] 7.08 Export CSV (dashboard-funnel.spec exports; test_dashboard_funnel exports)
- [x] 7.09 Empty, loading, error states (states dashboard-no-account, first-run, campaign-totals, live-feeds; funnel 'unavailable' test)
- [x] 7.10 Numbers reconcile with the database (backend test) (test_dashboard_funnel (counts reconcile with rows; daily export adds up to invitations sent))
- [~] 7.11 Axe, 360/768/1280, both themes (axe and 360 px pass for all dashboard states; 768 px and screenshots not yet viewed)

## Area 8: AI assistant
- [x] 8.01 Voice and text assistant exists (Deepgram Voice Agent) (existing voice and text assistant; test_assistant (38 tests))
- [x] 8.02 Provider interface for STT, TTS and LLM: Deepgram, or local Ollama + Whisper + Piper (test_assistant_speech)
- [x] 8.03 Local option: Whisper STT (faster-whisper, MIT, optional) (test_assistant_speech; assistant-microphone.spec)
- [x] 8.04 Local option: Piper TTS for spoken replies (test_assistant_speech 'piper speaks a reply')
- [x] 8.05 Local option: Ollama model (test_assistant_local (7 tests); assistant-local.spec 'ready' (typed requests only))
- [x] 8.06 Settings choice of provider with cost, where it runs, licence and readiness; local refused while Ollama is not ready (assistant-providers.spec; test_assistant_speech)
- [x] 8.07 Tools: accounts (list, limits, status) (list_sender_accounts, explain_account_status, suggest_limits (test_assistant))
- [x] 8.08 Tools: leads (add, lists, do-not-contact) (search_leads, get_lead, create_lead_list, add_do_not_contact (test_assistant, test_assistant_local NewToolsTest))
- [x] 8.09 Tools: campaigns (create, pause, resume, status) (search_campaigns, get_campaign, create_campaign_draft, set_campaign_state (test_assistant))
- [~] 8.10 Tools: inbox (find conversation, draft reply) (search_conversations (read) and draft_message exist; saving a reply draft into a conversation is not a tool)
- [x] 8.11 Tools: dashboard (answer questions) (get_dashboard_summary, get_funnel (test_assistant_local NewToolsTest))
- [~] 8.12 Tools: settings (read-only unless confirmed) (set_daily_limits and set_account_state exist as confirmed proposals; no tool reads the settings screens)
- [x] 8.13 Every action tool asks confirmation and obeys ceilings (test_assistant ConfirmationTest includes every write tool; test_assistant_local write tool makes a card and changes nothing)
- [x] 8.14 Works with no paid service configured (text with local model) (test_assistant_local: typed assistant with no paid service configured)
- [~] 8.15 Transcript, mute, stop, error states (existing panel has transcript, mute and errors; the local card shows the conversation and errors; not re-audited)
- [~] 8.16 Axe, 360/768/1280, both themes (axe and 360 px pass for settings (with the local card); the existing assistant panel states were passing before)

## Area 9: Templates and saved replies
- [x] 9.01 Message templates: create, edit, delete, search (existing Templates page (create, edit, delete, copy, search); templates-and-sequences.spec; test_templates_and_sequences)
- [x] 9.02 Variables inside templates (variables in the editor (builder chips, MessageEditor); render preview test_message_variables)
- [x] 9.03 Insert a template into the editor or reply box (templates-and-sequences.spec ('offered in the message editor'; inbox reply insert))
- [x] 9.04 Saved replies for the inbox with shortcut (templates-and-sequences.spec ('/shortcut plus a space expands it'); test_templates_and_sequences ShortcutTest)
- [x] 9.05 Sequence templates (links to 5.F16) (templates-and-sequences.spec ('four bundled templates and earlier campaigns'))
- [x] 9.06 Share sequence (export and import file) (Share sequence file and Import sequence: test_templates_and_sequences SequenceFileTest; templates-and-sequences.spec; campaigns-list.spec)
- [~] 9.07 Empty, loading, error states (existing templates page states; new dialogs have empty text; no dedicated loading or error test)
- [~] 9.08 Axe, 360/768/1280, both themes (axe and 360 px pass for the touched pages (campaigns, builder, inbox, settings); a templates page state is not in the axe list)

## Area 10: Settings and integrations [6]
- [x] 10.01 Settings page exists (audit) (settings page and the new /settings/integrations page)
- [x] 10.02 Notifications: notification emails (integrations.spec notifications; test_integrations NotificationTest)
- [x] 10.03 Notification toggles: account connected, disconnected, any message (integrations.spec notifications (toggles saved); test_integrations)
- [x] 10.04 Campaign-related notification settings (campaign paused and launched toggles; test_integrations 'an event emails only when that notification is on')
- [~] 10.05 Notifications actually sent (local email provider interface, test) (test_integrations: emails are written to the outbox and sent through SMTP when configured; events wired: reply received, account disconnected, campaign launched, interested label; 'account connected' and 'campaign paused' events are not emitted yet; real SMTP not exercised)
- [x] 10.06 Webhook: URL, events, test button, signing secret, delivery log (integrations.spec webhooks; test_integrations WebhookTest (signature, delivery log, test button, private addresses refused))
- [x] 10.07 API keys: create (shown once), revoke, last used (integrations.spec API keys; test_integrations KeyAndApiTest (shown once, hashed, revoked))
- [~] 10.08 Public API reference page (endpoints are listed on the API tab; no generated reference page)
- [x] 10.09 Slack integration (webhook-based) (integrations.spec webhooks (Slack type); test_integrations (only hooks.slack.com accepted))
- [~] 10.10 HubSpot: import contacts, sync outreach status (Unverified LV of HubSpot) (test_integrations HubSpot import with a stand-in; built from HubSpot's public docs, unverified on a real account; syncing outreach status back is not built)
- [x] 10.11 Email-tool exports for Smartlead and Instantly formats (integrations.spec email tools; test_integrations exports)
- [x] 10.12 MCP server for AI clients (test_integrations KeyAndApiTest (MCP: initialize, tools/list, tools/call; read and draft tools only))
- [~] 10.13 Migration importer (competitor export files) (test_integrations importer for leads and lists from another tool's CSV; campaigns and conversation history are not imported)
- [x] 10.14 Usage meter (replaces credits and billing) (integrations.spec usage; test_integrations usage)
- [~] 10.15 Support page with contact form (local mail provider) (integrations.spec support; messages are saved in the workspace, not emailed)
- [x] 10.16 Profile settings: name, phone, designation, company (settings-profile.spec; test_profile_and_news)
- [~] 10.17 Social post planner: board and calendar views (existing publishing module (Studio, Calendar, Queue); not re-audited this stretch)
- [~] 10.18 Post editor: title, account, copy (3,000), mentions, media, first comment (1,250) (existing post editor; not re-audited)
- [x] 10.19 Post review workflow: private reviewer links (shown once, hashed, 14 days, revocable), feedback thread with replies, approval per post version that never publishes (test_post_reviews; post-review.spec)
- [~] 10.20 [LV:mock] Post publishing through paced tasks within a ceiling (Unverified LV) (existing publishing; Unverified LV)
- [x] 10.21 [LV:mock] Manual engagement: six reactions and comments from a chosen sender, within its own ceiling of 25, with a history and cancel (test_engagement; engagement.spec)
- [x] 10.22 What's new panel with an unread dot (settings-profile.spec; test_profile_and_news)
- [~] 10.23 Language and appearance settings (light and dark themes exist; no language setting)
- [~] 10.24 Every control works or is disabled with "Coming soon" (new screens have no inert controls (disabled items say why); a scan of every older screen is part of area 12)
- [x] 10.25 Axe, 360/768/1280, both themes (axe and 360 px pass for six integrations tabs and settings, both themes)

## Area 11: Safety
- [x] 11.01 Ceilings for every task type; test fails if one is missing (test_ceilings_cover_every_type)
- [x] 11.02 New accounts start at 0 (test_new_account_limit)
- [x] 11.03 Weekly invite ceiling 150 enforced (test_outreach 'weekly connection cap', 'weekly invite ceiling holds')
- [x] 11.04 Daily total 200 enforced (test_safety_area 'daily total is held at 200')
- [x] 11.05 Varying daily limits (range) applied (test_account_policy 'presets ranges and repeatability')
- [x] 11.06 Ramp-up never exceeds ceilings, a stopped action never restarts (test_safety_area ramp-up tests)
- [x] 11.07 [LV:mock] Auto-pause on LinkedIn warning, checkpoint, restriction (test_outreach checkpoint, restriction and logged-out tests)
- [x] 11.08 Random gaps between actions, never a burst (test_safety_area GapTest)
- [x] 11.09 [LV:mock] Stale-invite withdrawal executes within limits (backend/tests/test_withdraw.py)
- [x] 11.10 Sender health page: account Health tab plus the Safety page (account-management.spec health; safety.spec)
- [x] 11.11 Kill switch: stops everything at once, admin-only control with confirmation (test_outreach kill switch tests; safety.spec)
- [x] 11.12 Operating hours enforced (test_outreach working hours tests)
- [x] 11.13 Test account profile (5 views, 5 requests, 5 messages, the rest stopped) applied from the Sender limits tab (test_safety_area TestProfileTest; safety.spec)
- [x] 11.14 Audit log of every action with its reason, workspace-only, paged and filtered (test_safety_area AuditTest; safety.spec)
- [x] 11.15 Secrets never logged (test_safety_area SecretsTest; test_security_surfaces LogHygieneTest)

## Area 12: Design and quality
- [ ] 12.01 docs/DESIGN.md current with all components
- [ ] 12.02 Every screen in both themes at 360, 768, 1280
- [ ] 12.03 Contrast checks pass
- [ ] 12.04 Axe passes on every screen
- [ ] 12.05 Keyboard navigation on every screen
- [ ] 12.06 Loading, empty, error states on every screen
- [ ] 12.07 No inert controls (script scans for switches without handlers)
- [ ] 12.08 Full backend suite passes
- [ ] 12.09 Typecheck passes
- [ ] 12.10 Production build passes, bundle size recorded
- [ ] 12.11 Playwright suite passes against vite preview
- [ ] 12.12 docs/DEPENDENCIES.md complete with licences
- [ ] 12.13 Worktree report
- [ ] 12.14 End-to-end scenario on mock site
- [ ] 12.15 Platform-complete handover note

## Counts per area
Total 344 lines (2026-11-16). Done / partial / open:
- Area 3: 66 lines (31 done, 3 partial)
- Area 4: 51 (0, 3)
- Area 5: 108 (0, 1)
- Area 6: 29 (0, 1)
- Area 7: 11 (0, 1)
- Area 8: 16 (0, 1)
- Area 9: 8 (0, 0)
- Area 10: 25 (0, 1)
- Area 11: 15 (2, 0)
- Area 12: 15 (0, 0)

The lines will be split further at each area's audit when a screen turns out to have more fields than listed here.
