# Area 4: Leads (report)

Date: 2026-11-16. Branch `local-complete`. Local only; nothing pushed or deployed.
Source: OutFlo report sections 5 and 6.1, gap item 7, and our extras. Checklist lines 4.A to 4.E in `docs/CHECKLIST.md`.
LV = not verified on real LinkedIn (no access, or no GO yet).

## Table

| Item | Status before | What I did | Test | Result |
|---|---|---|---|---|
| Source picker with reasons for unavailable sources | Partial | Added a reason line per source; "Coming soon" for the group source | add-leads.spec "every source is listed" | pass |
| Estimate before every import | Partial (rough text) | Server estimate (people, page loads, minutes) shown before anything is created, plus how many page reads the account has left today | add-leads.spec (2 tests); test_lead_sources_more estimate | pass |
| Preview before saving | Works | Unchanged | test_lead_collections | pass |
| Pasted profile links, CSV, Google Sheets, saved lists, inbox contacts, my connections | Works | Unchanged. CSV: added a sample file link and a clear 5 MB message | add-leads.spec; test_lead_collections | pass |
| LinkedIn search, post reactions or comments | Partial | Post links are now checked (activity, ugcPost, share, posts) with a message saying how to copy the right link | test_lead_sources_more | pass; LV |
| LinkedIn event attendees | Missing | Collector, address check, "account must be attending" warning | test_lead_sources_more (collector, validation) | built, LV |
| People who engaged with my own posts | Missing | Collector over the sender's five latest posts | test_lead_sources_more | built, LV |
| Sales Navigator leads, Recruiter search | Missing | Collectors (card links become profile addresses), address checks, 2,500 maximum | test_lead_sources_more | built, LV: no access |
| LinkedIn companies, Sales Navigator accounts | Missing | Company collectors and company lists (not people, never messaged): list, view, add all to do-not-contact, delete | test_lead_sources_more; leads-extras.spec | built, LV |
| LinkedIn group | Missing | Shown as "Coming soon" with the reason; cannot be started | test_lead_sources_more; add-leads.spec | disabled on purpose |
| Custom campaign variables per lead | Missing | Stored on the lead, validated (names, reserved names, 500 characters, 20 maximum), filled into messages as `{{name}}`, editable in the lead form | test_lead_variables (3); leads-extras.spec | pass |
| Lead details: campaigns, history, "Lead not present in any campaign" | Missing | Overview endpoint and dialog | test_lead_overview (4); leads-extras.spec | pass |
| Add a lead to a campaign | Missing | Adds to the campaign's list; starts the sequence on an active campaign; refused for a do-not-contact lead or a campaign without a list | test_lead_overview; leads-extras.spec | pass |
| Do-not-contact: people and companies | Missing | New list under Leads: add by lines, CSV import and export, search, remove; companies matched by name ignoring case and punctuation | test_do_not_contact (8); do-not-contact.spec (3) | pass |
| Do-not-contact enforced | Missing | Checked at import, at launch, and again before every action (a queued action is skipped) | test_do_not_contact EnforcementTest | pass |
| Lead lists: create, edit, delete | Works | Unchanged | none new | partial evidence |
| Leads table: filters, bulk actions, export | Works | Unchanged | leads-columns.spec only | partial evidence |
| Lead list search, filter and export | Missing | Not built | none | open |

## Verification

- Backend: new tests this area: do-not-contact 8, lead variables 3, extra sources 9, lead overview 4. Full backend suite: 410 tests, 0 failed (360 s). Typecheck clean.
- Playwright (dev server): add-leads 6, do-not-contact 3, leads-extras 4 pass. Axe and 360 px checks pass for leads, leads-lists, leads-companies, leads-do-not-contact, leads-add-sources and leads-add-event-form, both themes.
- Screens in `docs/reports/screens/area-4/` (both themes, 360, 768 and 1280). I looked at the event form at 360 dark and the do-not-contact tab at 1280 light.
- Real LinkedIn: no source was run on real LinkedIn this stretch (needs your GO). The older sources (search, post, connections) remain LV too.

## Open
1. Lead list screen: search, filter and export on lists; a dedicated test for the leads table filters and bulk actions.
2. Keyboard walk-through of the picker and each form is not a dedicated test (the dialog traps focus, Radix).
3. Sales Navigator, Recruiter, event, company and own-post readers need a real account and your GO to verify.
4. Hosted database: new tables `do_not_contact`, `company_lists`, `company_entries`, new column `leads.variables`. `run_simple_migrations` adds the column and `create_all` adds the tables.

## Standing reminders
- Secret scan broken in CI (deferred by the owner on 15 Nov 2026; must be fixed and run on full history before any public repo or real user).
- Clerk secret and CockroachDB password were exposed in chat on 15 Nov 2026 (rotation deferred; mandatory before any real user, pilot, production deploy or public repo).
