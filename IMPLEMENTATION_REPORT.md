# Implementation report — 5 November 2026

The browser extension remains optional. People can sign into SYNEX with LinkedIn, and workspace administrators can separately authorize an account for member publishing. Installing the extension is unnecessary for either flow or for scheduled publishing.

| Status | Outcome |
| --- | --- |
| Completed and verified locally | Revocable sessions; explicit account linking; durable drafts and schedules; calendar, activity and worker diagnostics; manual contacts, lists and templates; extension draft handoff; protected workspace reads and writes. See TEST_REPORT.md for evidence. |
| Implemented but not live-verified | Official LinkedIn sign-in, consent, profile verification, reconnect/disconnect, member text posts and single JPEG/PNG posts. Tests exercised local provider responses. A provider post identifier is required for success. |
| Blocked by missing credentials | This installation lacks a LinkedIn client ID and secret. Password reset delivery and optional AI suggestions also need their own configured providers. |
| Dependent on LinkedIn approval | The registered application must have Sign In with LinkedIn using OpenID Connect and Share on LinkedIn access. Its product grants have not been verified. |
| Not implemented | Organization publishing, video/document publishing, LinkedIn engagement analytics and verified team invitations. Scraping, cookie import, automatic outreach and private LinkedIn API calls are excluded. |

## Changes to the existing application

The React workspace now uses stored records for its overview, editor, calendar, activity, and analytics. Scheduling and approval are separate from drafting. The worker records attempts, pauses disconnected accounts and sends uncertain delivery outcomes for review instead of submitting a possible duplicate. Uploads are restricted to validated images owned by the workspace. Sessions use HTTP-only cookies, and publishing credentials are encrypted independently of platform sessions.

The browser extension uses browser storage to retain a draft and opens SYNEX for review. It has no LinkedIn host or cookie permission. Historical outreach records remain available without the previous unattended actions. Connecting a publisher cannot create a SYNEX login for that LinkedIn member.

## Data and rollout

Applied the migration to the supplied SQLite database after verifying a trial upgrade. Business data in all 17 original tables was checked for preservation. Retired private integration secrets were excluded from the backup; the backup is at backend/backups/pre-publishing-20261105-060823.db. A dedicated encryption key was provisioned locally. Back up that key separately from the database. The supplied folder contains no Git history.

Local preview uses frontend port 5173 and API port 8010. README.md covers startup and production requirements; LINKEDIN_INTEGRATION.md covers the exact callback, permissions, and provider boundaries. No deployment, production load certification, or live LinkedIn write was performed.
