# OutFlo, checked live on 2026-11-19 (read-only)

Navigation (left rail, icons): Dashboard `/dashboard`, Unibox `/inbox`, Campaigns `/allcampaigns`, LinkedIn Accounts `/accounts`, Others `/others` (lead lists, do not contact, social engagement), What's new, Rewards `/others/rewards`, Help, Settings.

## Area 3: LinkedIn accounts

**List `/accounts`**: title "LinkedIn Accounts", button "+ Connect account" top right.
- Card "Organization overview" with "Manage plan" and "View credits": Plan (Growth, Trial badge, "Trial ends Nov 22, 2026"), Seats available (2, "1 used · 3 total"), Credits granted (100, "Includes purchases"), Credits remaining (100, "Available for messages and audio").
- A TABLE, not cards. Columns: LinkedIn account (with a search icon), Status (with a filter icon), Usage (last 24 h) (with an info icon), Performance. Row: avatar, name, "0 active campaigns"; globe icon, "Connected" and "Active" badges; usage chips "0/23–27" (connections), "0/28–32" (messages), "SMART" pill; performance chips (accepted %, reply %); a chevron opens the account. Footer "Showing 1-1 of 1", Previous, Next.

**Account page `/accounts/:id?tab=`**: "Back to Accounts"; a header card with a coloured banner, SSI box (OutFlo SSI 15, Top 95%, Confidence Medium), large avatar, name, headline, refresh and LinkedIn icons, "Resync", location, company, globe, Connected and Active badges, "CONNECTED BY LOGIN CREDENTIALS SINCE Nov 15, 2026".
- Tabs in this order: Sender Limits, Inbox Privacy, Health, Account, Manage Connections, AI Configuration.
- Sender Limits: recommendation banner ("We reviewed your LinkedIn profile and activity and recommend daily sending limits", Apply limits, Keep current, Show suggestions); info box (limits are per account; profile-related actions max 100 a day; daily activity varies; Read more); "Smart Auto-Increase" with four buttons Conservative (+1 per week), Balanced (+2 every 2–3 days), Aggressive (+3 daily), Custom per-limit; "Daily limits" with Range chips ±1 … ±10; then one ROW per metric: name, a one-line description, "23–27 / day", "max 40", "Auto-increase off"; a row expands to Increase by, Stop at, Increase every (Dynamic (recommended), Every day, 2 days, 3 days, week, 2 weeks, month) and a sentence ("OutFlo AI will increase … by +2 … Stops at 40/day"). Shown first: Profile views, Connection requests (with a warning), Messages (note: voice notes use the message quota), Post likes; "Show More Limits" reveals Is Active on LinkedIn, Profile follows, Withdraw invites, Paid InMails, Free InMails, Connection checks.
- Inbox Privacy: "Full inbox sync / All LinkedIn conversations tracked"; "Account access required" when someone else connected it; "SHARE WITH ACCOUNT OWNER" link.
- Health: only "Auto-withdraw stale invites" (RECOMMENDED) with the why-text and a guide link.
- Account: Deactivate seat (Deactivate), Delete account (Delete).
- Manage Connections: Reload; Connection List / Invitations; "Your connections sync gradually"; 5,000+ advice; Known connections count; Export CSV, Upload CSV; search; list.
- AI Configuration: "Assigned voice / No voice assigned / Assign voice".

**Connect account**: a RIGHT-SIDE DRAWER "Add LinkedIn Account": three cards: Connect via Extension (Recommended), Connect with Credentials, Share Connection Link (the link, Copy, "How to use this link"). Credentials: "Back to options", Organization Email chip with Change, Email or Phone, Password, collapsible "Sync Preferences" (Conversation import: Track and import all LinkedIn conversations / Import only conversations starting from OutFlo), "Connect Account", "Set Proxy Configuration".
