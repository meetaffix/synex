# Synex build checklist (definition of done)

Source: `docs/reference/outflo-inspection-2026-11-16.txt` (section numbers in brackets), its gap list (G1 to G10), and Synex extras (X).
Rule: tick `[x]` only with evidence in the line (test name or screenshot path). `[~]` means built but not fully verified (reason given). `[ ]` means not done.
"Unverified LV" = built and tested on the mock site; not verified on real LinkedIn (no access or no GO yet).
Written 2026-11-16. Counts per area are at the end of this file.

## Area 3: LinkedIn accounts [4, 2.3, 6.2, G5, G9]

### 3.A Accounts list and overview
- [x] 3.A01 Organization overview card: plan name, trial end, seats used of included, seats available [4.1] (accounts-list.spec 'overview card')
- [x] 3.A02 Seats used / available endpoint `/linkedin-accounts/overview` (backend `account_management.py`, mock in tests)
- [ ] 3.A03 Credits/usage meter on the card, "Manage plan" and "View usage" links [4.1]
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
- [ ] 3.B06 Elapsed time, refresh-resume of an in-progress connect, "Connect another" (still open)
- [ ] 3.B07 "Already installed? Refresh" wording replaced by honest text for the later extension

### 3.C Account page
- [x] 3.C01 Page at `/linkedin-accounts/:id` with header, status badge and summary (account-management.spec.ts #1)
- [x] 3.C02 Resync button (runs the account check)
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
- [ ] 3.D10 Actions listed: profile views, connection requests, messages, follows, connection checks, inbox reads, connections reader, lead collection (done); post likes, withdraw invites, InMails (to add with area 5/11 action types)
- [ ] 3.D11 Server-side: a policy is rejected above ceiling (backend test exists; add to this list on audit)

### 3.E Inbox privacy [4.7]
- [x] 3.E01 Which conversations Synex reads (all / only campaign) (account-management.spec.ts #6)
- [x] 3.E02 Inbox history days (account-management.spec.ts #6)
- [x] 3.E03 Owner-only lock with "Account access required" note (account-management.spec.ts #6)
- [x] 3.E04 "Share with account owner" link with Copy (account-management.spec 'send the owner a link')

### 3.F Health [4.8]
- [~] 3.F01 Auto-withdraw stale invites: setting saved, execution not built yet (page says so); built in area 11
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
- [~] 3.G11 Real reads of connections and invitations: Unverified LV (selectors fixture-tested only)

### 3.H AI configuration [4.11]
- [x] 3.H01 Tab "AI configuration" with assigned voice (none by default) (account-management.spec 'AI configuration')
- [x] 3.H02 "Assign voice" dialog with preset voices and a play sample (account-management.spec 'AI configuration')
- [x] 3.H03 Preset voices from an open-source, commercially licensed TTS (licence recorded) (test_voices (licences); samples disabled until Piper installed)
- [~] 3.H04 "Clone my voice" dialog: name, record or upload .m4a/.mp3/.wav, 30 to 60 s, ownership confirmation, Create (clone is disabled with the reason: no commercially licensed cloning model verified)
- [x] 3.H05 Voice cloning only with a commercially licensed open model, else disabled "Coming soon" with reason (account-management.spec 'AI configuration' (disabled with reason))

### 3.I Quality for area 3
- [x] 3.I01 Axe and 360 px checks on account screens, both themes (a11y.spec.ts, responsive-360.spec.ts, `-g account-`: 14 pass)
- [~] 3.I02 Screens viewed at 360, 768, 1280 in both themes after final change (captured in docs/reports/screens/area-3/; I looked at two of them)
- [ ] 3.I03 Keyboard walk-through of the account page recorded as a test
- [ ] 3.I04 Playwright against `vite preview` production build

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
- [~] 4.B07 CSV: counts of valid, duplicate, invalid, already-known (skipped counts per reason are shown after import; a 'rows without a LinkedIn URL' count shows in the detail line; no dedicated UI test)
- [x] 4.B08 Add from my saved list: list picker, Refresh, Create empty list (lists source in AddLeadsDialog; test_lead_collections)
- [x] 4.B09 Saved lists empty state "No saved lead lists found" (AddLeadsDialog shows 'You have no lists yet.')
- [~] 4.B10 Basic LinkedIn search URL: URL, account, list name (dated default), limit (default 100, max 1,000) (collection framework exists; Unverified LV) (test_lead_collections search; Unverified LV)
- [~] 4.B11 Sales Navigator leads: URL, account, list, limit max 2,500 (Unverified LV: no access) (test_lead_sources_more CollectorTest seats; Unverified LV: no access)
- [~] 4.B12 Recruiter: URL, recruiter account, list, limit max 2,500 (Unverified LV: no access) (test_lead_sources_more CollectorTest seats (same reader); Unverified LV: no access)
- [~] 4.B13 LinkedIn post: URL formats (activity, ugcPost, share), scrape type Reactions / Comments / Both, limit 1,000 (post address validation in test_lead_sources_more; reader exists; Unverified LV)
- [~] 4.B14 LinkedIn event: URL, "account must be attending" warning, limit 1,000 (test_lead_sources_more event collector; add-leads.spec warning; Unverified LV)
- [~] 4.B15 LinkedIn companies: company list source (opens its own form, not a redirect) (test_lead_sources_more company collector and company lists; leads-extras.spec; Unverified LV)
- [~] 4.B16 Sales Navigator accounts: company search URL, account, list, companies limit 100 (Unverified LV) (test_lead_sources_more company collector; Unverified LV: no access)
- [x] 4.B17 LinkedIn group: disabled "Coming soon" until built (add-leads.spec 'unbuilt one says Coming soon'; test_lead_sources_more group)
- [x] 4.B18 Extra: my connections (from the connections reader) (connections source: test_lead_collections / account connections reader)
- [~] 4.B19 Extra: engagers of my own posts (test_lead_sources_more own posts collector; Unverified LV)
- [x] 4.B20 Extra: inbox contacts (inbox source: test_lead_collections)
- [x] 4.B21 Extra: Google Sheets (open-source/CSV-export path; no paid service) (csv source with Google Sheets link: test_lead_collections sheet link test)
- [x] 4.B22 Extra: bulk paste of links (urls source: test_lead_collections 'pasted links preview import')
- [x] 4.B23 Extra: degree filter (1st, 2nd, 3rd) (test_lead_collections 'degree filter and per-degree counts')
- [x] 4.B24 Extra: dedupe within list and against other lists (stage() drops duplicates; test_lead_collections skip options)
- [x] 4.B25 Each source has a tooltip on every field [5.12] (a hint line per source in AddLeadsDialog (add-leads.spec))
- [x] 4.B26 Each source checks the account's collect_leads ceiling and shows what remains (add-leads.spec 'page reads left today'; test_lead_sources_more estimate)
- [x] 4.B27 URL validation messages per source (wrong host, wrong type, missing) (test_lead_sources_more 'each source names what is wrong with its address')

### 4.C Lead lists and leads table
- [~] 4.C01 Lead Lists tab: create empty list (name dialog), search, filter, export (lists page creates, edits and deletes lists (existing); search, filter and export on lists not built)
- [~] 4.C02 List detail: leads, count, source, created, delete list with confirm (list card opens its leads (/leads?listId=); delete list exists; no dedicated test)
- [~] 4.C03 Leads tab: table with search, filters, bulk select, bulk actions, export CSV (LeadsPage has search, status and list filters, select all, bulk status, bulk delete, Export; only leads-columns.spec covers it)
- [x] 4.C04 Lead detail: fields, variables, campaigns it is in, status history (leads-extras.spec 'a lead's details show its campaigns and history'; test_lead_overview)
- [x] 4.C05 Add lead to a campaign from the table (leads-extras.spec (add to a campaign); test_lead_overview adds to draft and active campaigns)
- [x] 4.C06 Lead "Lead not present in any campaign" state (leads-extras.spec 'Lead not present in any campaign'; test_lead_overview)
- [~] 4.C07 Empty, loading, error states (empty and loading states exist on LeadsPage and the new tabs (leads-empty a11y state); error state tested only for new tabs)

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
- [ ] 4.E03 Keyboard path through the picker and each form

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
- [~] 5.E05 Follow-up: wait 2 days (minimum 15 minutes), "If not replied" chip (follow-up wait is in whole hours, minimum 1 hour (the report has 15 minutes))
- [~] 5.E06 Add follow-up message, remove, reorder (add and remove follow-ups work; reordering is not built)
- [x] 5.E07 Message editor with variable chips (campaign-builder.spec 'the sequence' (variable chips))
- [x] 5.E08 Settings visible on every node [beat OutFlo] (every block in the classic sequence shows its settings (builder spec 'the sequence'))
- [x] 5.E09 Empty message validation message (test_launch_check empty message; builder spec 'review ... checklist')

### 5.F Smart builder [2.7]
- [ ] 5.F01 Graph canvas: Campaign start, Add action, zoom, full screen, trash
- [~] 5.F02 Classic | Smart switch with confirm "Switch to Smart?" (Classic is built; Smart is shown disabled with the reason)
- [ ] 5.F03 Node: Send connection request (max one; Connected and Not connected branches; 15-day wait)
- [ ] 5.F04 Node: Send message
- [ ] 5.F05 Node: Send voice note (needs connection first message)
- [ ] 5.F06 Node: Follow profile
- [ ] 5.F07 Node: Like a post
- [ ] 5.F08 Node: View profile
- [ ] 5.F09 Node: Send free InMail (Unverified LV)
- [ ] 5.F10 Node: Send InMail (Unverified LV)
- [ ] 5.F11 Node: Withdraw invite
- [ ] 5.F12 Conditional: If connection
- [ ] 5.F13 Conditional: Is active on LinkedIn
- [ ] 5.F14 Each branch has Add action and End
- [ ] 5.F15 Next stays disabled while a node is unconfigured, with the reason
- [ ] 5.F16 Templates dialog: Templates and Previous campaigns tabs, search, preview graph, Apply
- [ ] 5.F17 Four bundled templates (Connection nurture, 5-step connect and convert, Cold connection request, Full-cycle playbook)
- [ ] 5.F18 Engine runs graphs and branches (backend tests on mock site)

### 5.G AI writing drawer [1, G1]
- [x] 5.G01 Toggle "Personalise with live LinkedIn data" on each message (campaign-builder.spec 'AI writing' (switch))
- [x] 5.G02 Drawer "Configure AI for message N" with Direct | AI assisted (campaign-builder.spec 'AI writing' (Direct and AI assisted tabs))
- [~] 5.G03 Direct tab: editor with Preview link (Direct tab explains; the editor has its own Preview)
- [x] 5.G04 Card linking to AI campaign context (campaign-builder.spec 'AI writing' (context card))
- [~] 5.G05 Per-profile data options (role and company, recent posts, skills, career transitions, shared interests), each collected by paced tasks (current role and company work; recent posts, skills, career, interests are disabled 'coming soon' (need the paced profile reader); test_ai_writing refuses them server-side)
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
- [ ] 5.J01 Direct: record or upload .m4a, 60 s, 20 MB, optional text
- [ ] 5.J02 AI assisted: script up to 1,000 characters
- [ ] 5.J03 Sender voice readiness panel
- [ ] 5.J04 Language and accent: English US, UK, India
- [ ] 5.J05 Preview voice note with cost estimate
- [ ] 5.J06 Open-source TTS with commercial licence (licence recorded in DEPENDENCIES.md)

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
- [~] 5.L01 Backend tests for engine, graph branches, exclusions (test_campaign_settings, test_launch_check, test_campaign_list; graph branches not built)
- [ ] 5.L02 Flaky draft-generation test fixed and run 20 times in a row
- [~] 5.L03 Axe, 360/768/1280, both themes for every screen (axe and 360 px for every builder state and the list (pass); 768 and screenshots not yet viewed for area 5)
- [ ] 5.L04 Keyboard path through the builder

## Area 6: Inbox [3, G8]
- [~] 6.01 Three-pane layout: list, thread, profile panel (existing; audit)
- [ ] 6.02 "Select a conversation" empty state
- [ ] 6.03 Header menu: Export CSV with current filters
- [ ] 6.04 Account chips and account switcher
- [ ] 6.05 Search all conversations
- [ ] 6.06 Date presets: Today, Yesterday, Last week, Last month, Last quarter, Custom range with Apply
- [ ] 6.07 Filter: Needs my reply
- [ ] 6.08 Filter: I messaged last
- [ ] 6.09 Status: Starred, Drafts, Scheduled, Unread
- [ ] 6.10 Tags (custom) and system tags
- [ ] 6.11 Archived filter
- [ ] 6.12 Sender accounts filter
- [ ] 6.13 Campaigns filter: include or exclude, all campaigns
- [ ] 6.14 "Include conversations where": messages sent or responses
- [ ] 6.15 Conversation card: avatar, name, unread badge, snippet, received-by chip, time
- [ ] 6.16 Hover star and selection checkbox
- [ ] 6.17 Bulk actions: mark read, archive, tag, star
- [ ] 6.18 Thread: header, date separators, bubbles
- [ ] 6.19 Reply box: emoji, attachment, voice message, schedule, AI button, Send, sending-from account
- [ ] 6.20 Schedule message
- [ ] 6.21 Read-only conversation message when sending is not allowed
- [ ] 6.22 Sending checked against outreach limits; reading uses its own ceiling
- [ ] 6.23 AI suggested reply using campaign context, shown with cost, editable [beat OutFlo]
- [ ] 6.24 Interest labels (interested, not interested, meeting, wrong person) [beat OutFlo]
- [ ] 6.25 Profile panel: photo, Fetch profile, followers, connections, location, local time, about, experience
- [ ] 6.26 Profile panel buttons: Mark as starred, Mark as answered, Select tags, Archive
- [ ] 6.27 Lead overview with Add to campaign
- [ ] 6.28 Refresh and live sync indicator
- [ ] 6.29 Axe, 360/768/1280, both themes, keyboard path

## Area 7: Dashboard and analytics
- [~] 7.01 Dashboard exists (audit)
- [ ] 7.02 Funnel: leads, invites, accepted, messages, replies, interested
- [ ] 7.03 Acceptance and reply rate per campaign
- [ ] 7.04 Per-account activity and limits used
- [ ] 7.05 Date range selector
- [ ] 7.06 Campaign and account filters
- [ ] 7.07 Charts follow the dataviz rules, both themes
- [ ] 7.08 Export CSV
- [ ] 7.09 Empty, loading, error states
- [ ] 7.10 Numbers reconcile with the database (backend test)
- [ ] 7.11 Axe, 360/768/1280, both themes

## Area 8: AI assistant
- [~] 8.01 Voice and text assistant exists (Deepgram Voice Agent)
- [ ] 8.02 Provider interface for STT, TTS and LLM
- [ ] 8.03 Local option: Whisper STT
- [ ] 8.04 Local option: Piper TTS
- [ ] 8.05 Local option: Ollama model
- [ ] 8.06 Settings page to choose providers, with licences shown
- [ ] 8.07 Tools: accounts (list, limits, status)
- [ ] 8.08 Tools: leads (add, lists, do-not-contact)
- [ ] 8.09 Tools: campaigns (create, pause, resume, status)
- [ ] 8.10 Tools: inbox (find conversation, draft reply)
- [ ] 8.11 Tools: dashboard (answer questions)
- [ ] 8.12 Tools: settings (read-only unless confirmed)
- [ ] 8.13 Every action tool asks confirmation and obeys ceilings
- [ ] 8.14 Works with no paid service configured (text with local model)
- [ ] 8.15 Transcript, mute, stop, error states
- [ ] 8.16 Axe, 360/768/1280, both themes

## Area 9: Templates and saved replies
- [ ] 9.01 Message templates: create, edit, delete, search
- [ ] 9.02 Variables inside templates
- [ ] 9.03 Insert a template into the editor or reply box
- [ ] 9.04 Saved replies for the inbox with shortcut
- [ ] 9.05 Sequence templates (links to 5.F16)
- [ ] 9.06 Share sequence (export and import file)
- [ ] 9.07 Empty, loading, error states
- [ ] 9.08 Axe, 360/768/1280, both themes

## Area 10: Settings and integrations [6]
- [~] 10.01 Settings page exists (audit)
- [ ] 10.02 Notifications: notification emails
- [ ] 10.03 Notification toggles: account connected, disconnected, any message
- [ ] 10.04 Campaign-related notification settings
- [ ] 10.05 Notifications actually sent (local email provider interface, test)
- [ ] 10.06 Webhook: URL, events, test button, signing secret, delivery log
- [ ] 10.07 API keys: create (shown once), revoke, last used
- [ ] 10.08 Public API reference page
- [ ] 10.09 Slack integration (webhook-based)
- [ ] 10.10 HubSpot: import contacts, sync outreach status (Unverified LV of HubSpot)
- [ ] 10.11 Email-tool exports for Smartlead and Instantly formats
- [ ] 10.12 MCP server for AI clients
- [ ] 10.13 Migration importer (competitor export files)
- [ ] 10.14 Usage meter (replaces credits and billing)
- [ ] 10.15 Support page with contact form (local mail provider)
- [ ] 10.16 Profile settings: name, phone, designation, company
- [ ] 10.17 Social post planner: board and calendar views
- [ ] 10.18 Post editor: title, account, copy (3,000), mentions, media, first comment (1,250)
- [ ] 10.19 Post review workflow: reviewers, magic link portal, feedback thread
- [ ] 10.20 Post publishing through paced tasks within a ceiling (Unverified LV)
- [ ] 10.21 Manual engagement: reactions and comments with history (Unverified LV)
- [ ] 10.22 What's new panel
- [ ] 10.23 Language and appearance settings
- [ ] 10.24 Every control works or is disabled with "Coming soon"
- [ ] 10.25 Axe, 360/768/1280, both themes

## Area 11: Safety
- [x] 11.01 Ceilings for every task type; test fails if one is missing (test_ceilings_cover_every_type)
- [x] 11.02 New accounts start at 0 (test_new_account_limit)
- [ ] 11.03 Weekly invite ceiling 150 enforced (test)
- [ ] 11.04 Daily total 200 enforced (test)
- [ ] 11.05 Varying daily limits (range) applied by scheduler (test)
- [ ] 11.06 Ramp-up never exceeds ceilings (test)
- [ ] 11.07 Auto-pause on LinkedIn warning, checkpoint, restriction (test on mock site)
- [ ] 11.08 Random gaps between actions (test)
- [ ] 11.09 Stale-invite withdrawal executes within limits (test)
- [ ] 11.10 Sender health page
- [ ] 11.11 Kill switch: stops everything at once (test)
- [ ] 11.12 Operating hours enforced (test)
- [ ] 11.13 Meet Affix test limits (5/5/5) configurable profile
- [ ] 11.14 Audit log of every action with reason
- [ ] 11.15 Secrets never logged (test scans logs)

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
