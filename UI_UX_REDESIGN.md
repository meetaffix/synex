# UI / UX redesign

## Direction
Publishing-first B2B workspace: dark compact sidebar, off-white canvas, white writing surfaces, blue primary actions, Inter/system typography, restrained status colors. Hierarchy comes from alignment and spacing rather than decorative gradients or repeated cards.

## Changes across routes
- Overview: real account health, four internal counts, upcoming publishing and actual activity. Onboarding when disconnected, no invented performance graphs.
- Accounts: verified profile, permission list, expiry/last check, capability restrictions, reconnect and confirmed disconnect.
- Studio: account selector, internal title, plain-text editor, private single-image attachment and preview, character count, save feedback, LinkedIn preview, secondary writing assistance, search/filter library and explicit approval dialog.
- Calendar: month navigation, date selection, time zone, status marks, persistent post list; mobile uses compact markers. Week/drag-and-drop views deliberately omitted.
- Automation: a readable publishing queue rather than an arbitrary workflow canvas. Pause/edit/cancel and failed-result guidance live on the related post.
- Analytics: actual status distribution and internal publishing success rate with documented denominator. No LinkedIn reach/engagement claims.
- Activity: chronological records linked to posts.
- Settings: working profile/time-zone/password controls and administrator-only connection/worker diagnostics. Unsupported switches removed.
- Contacts/lists/templates: existing useful management retained under Resources and simplified with shared tokens; import restricted to authorized CSV; templates clearly represent manual drafts.
- Campaigns/conversations: preserved history and manual follow-up entry points, no misleading running controls.
- Auth: real LinkedIn sign-in plus email; fabricated testimonials and growth figures removed.
- Extension: retained and redesigned as an idea-capture companion.

## Removed or retired
45 unreachable frontend source files were removed after import-graph inspection: superseded shell/pages, old account pairing UI, marketing/demo components, decorative animation modules, unused UI wrappers. The current routes replace those screens. Removed unused Framer Motion, Recharts, and five Radix wrappers/packages. Historical database records were not deleted.

Private-API execution and cookie collection were removed from the extension/cloud executor. This is a replacement of unsupported execution, not removal of the extension. OAuth and durable server-side publishing are the supported execution path.

## Interaction and accessibility
Collapsible navigation with titles, mobile drawer with Radix focus trapping and Escape support, skip link, visible focus states, labeled forms, inline status/error messages, disabled publishing until permissions exist, confirmation before public publishing/disconnect, unsaved-change warning on app links and browser unload. Short color/opacity transitions; reduced-motion preference removes animations. No continuously animated decorations.

Desktop, tablet, and mobile screenshots were generated at 1440, 834, and 390 pixels. All 14 production routes were checked for horizontal overflow; representative screenshots were visually reviewed. This does not substitute for a full assistive-technology audit.
