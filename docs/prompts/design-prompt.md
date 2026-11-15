# Synex design prompt (Prompt DS)

Give this to Opus after the fix prompt (4F). It replaces item B2 of 4F, so tell Opus to skip B2 there.

---

You are a senior product designer and frontend engineer on Synex, a LinkedIn outreach platform. The owner has chosen the visual direction. Write it into the project as the single design reference, implement it as tokens, and bring every existing screen onto it. The owner cares most about this: the product must look designed, warm and polished, in both themes.

PROJECT: C:\Users\iamdn\Downloads\synex-zip\synex\frontend
Do not touch backend/. Do not copy OutFlo's or any other product's visual identity.

## Direction (decided by the owner)

- Feel: soft and friendly. Approachable, calm, rounded, generous spacing. Never corporate-grey, never loud.
- Themes: light and dark, user's choice. Default follows the system setting. A toggle in the user menu, remembered per user.
- Brand colour: teal-green.

## Step 1: Write the spec (docs/DESIGN.md in the project root)

This file is the reference for all future work. It must contain everything below, with final values after you verify contrast.

### Colour tokens

Starting values. Adjust only to pass contrast, and record the final values and measured ratios.

Light
- background: #F6F8F7, surface: #FFFFFF, surface-muted: #EEF3F1
- border: #E3E9E6, border-strong: #C9D4CF
- text: #12201C, text-muted: #51625C, text-subtle: #6B7C76
- primary: #0F766E, primary-hover: #0B5F59, primary-foreground: #FFFFFF
- primary-soft: #E3F4F1, primary-soft-foreground: #0B5F59
- success: #15803D on #E7F6EC, warning: #B45309 on #FEF3E2, danger: #B91C1C on #FDECEC, info: #1D4ED8 on #E8EFFD
- focus ring: #0F766E at 2px with 2px offset

Dark
- background: #0E1513, surface: #151E1B, surface-muted: #1B2623
- border: #25322E, border-strong: #34443F
- text: #E8EFEC, text-muted: #9DB0A9, text-subtle: #7F928B
- primary: #2DD4BF, primary-hover: #5EEAD4, primary-foreground: #06201C
- primary-soft: #12332E, primary-soft-foreground: #7FE7D8
- success, warning, danger, info: lighter foregrounds on dark tinted backgrounds, chosen by you and measured

Rules: every text/background pair meets 4.5:1 (3:1 for text 24px and larger and for UI boundaries). Status never relies on colour alone. Dark theme is designed, not inverted: surfaces get lighter as they rise, shadows are replaced by borders.

### Typography

- Family: Plus Jakarta Sans for everything, self-hosted from the project (no runtime request to a font CDN), weights 400, 500, 600, 700. Tabular numerals for all figures.
- Scale: 12/16, 14/20, 16/24, 20/28, 24/32 (size/line height). Nothing else.
- Page title 24/600. Section title 16/600. Body 14/400. Labels 14/500. Captions and table headers 12/500.

### Shape and space

- Spacing on the 4px grid: 4, 8, 12, 16, 24, 32, 48.
- Radius: 8 (inputs, small controls), 12 (buttons, menus), 16 (cards, dialogs), full (pills, avatars, status dots).
- Cards: surface colour, 1px border, 16 radius, 24 padding. Shadow only on floating layers (menus, dialogs), soft and low.
- Page gutters 32 desktop, 16 phone. Content max width 1280.
- Controls are 40px tall (36 compact in dense tables), touch targets at least 44 on phones.

### Components

Define each: anatomy, sizes, states (default, hover, focus, active, disabled, loading), light and dark.

Button (primary, secondary, ghost, danger), input, select, checkbox, radio, switch, textarea, badge and status pill, card, table, tabs, dialog, sheet, dropdown menu, tooltip, toast, empty state, skeleton, avatar, page header, sidebar item, metric card, filter bar.

- Primary button: filled teal, pill-shaped (full radius), 600 weight. One per view.
- Status pill: soft tinted background, matching foreground, a small dot, and the label.
- Sidebar: surface colour with a border (not a dark slab). The active item uses primary-soft with primary-soft-foreground text and a 12 radius.
- Empty states: a simple line illustration or icon in a primary-soft circle, a one-line title, one line of explanation, one primary action.
- Motion: 150ms ease-out for hovers and presses, 200ms for dialogs and sheets. Respect reduced-motion.

### Voice

Plain, warm, short. Sentence case. No exclamation marks, no jargon, no emoji.

### Do and don't

A short list with reasons: no gradients, no glows, no dark slab sidebar, no boxes inside boxes, no more than one primary action per view, no text under 12px, no placeholder-only labels.

## Step 2: Implement the tokens

- CSS variables for both themes and the Tailwind theme mapped to them. Semantic names only (background, surface, primary, ...). No raw hex anywhere in components.
- Theme switching without a flash on load. Follows the system by default; the user's choice is stored and wins.
- Update every primitive in src/components/ui to the spec. Remove the old shadcn default look where it differs.

## Step 3: Apply to every screen

Shell, dashboard, inbox, campaigns, sender accounts and all connect-flow states, reconnect page, leads, lead lists, templates, others, publishing pages, settings, help, and the auth pages (login, register, reset).

After this step nothing in the app uses the old look, and the 1,534-line global stylesheet is reduced to what is still needed. Report its new line count and what remains.

## Step 4: A living reference page

A route at /design (visible only in development) that renders every token and every component in every state, in the current theme. This is how the owner reviews the system.

## Step 5: Prove it

- Screenshots of every screen and every dialog state, in light AND dark, at 360, 768 and 1280 px, saved under frontend/test-results/review/<theme>/. Inspect every one yourself. List what you found and fixed per screen.
- The contrast table: every text/background pair in both themes with its measured ratio.
- Automated accessibility checks pass in both themes with zero serious or critical violations.
- npm run typecheck, npm run build, and all Playwright specs pass.

## Report back

The path to docs/DESIGN.md, final token values where you changed the starting values and why, the contrast table, files changed, the stylesheet's old and new line counts, the per-screen fix list for each theme, and real test output. State anything that still uses the old look.

---

# UX standard

Applies to every screen you build or touch. Work that fails it is rejected.

Before building: write the user's goal for the screen in one sentence, the primary action, and the steps to complete it. If a common task takes more than three clicks, redesign it.

## Layout and hierarchy

- One primary action per screen, visually dominant. Secondary actions are quieter. Destructive actions are never primary.
- Consistent page structure everywhere: title, one-line description, primary action, then content.
- Dense data goes in tables with sortable columns, sticky headers and sensible column widths. Numbers are right-aligned with tabular numerals.
- Related things are grouped; unrelated things are separated by space, not boxes inside boxes.

## Feedback

- Every action responds within 100 ms: pressed state, then a loading state, then a result.
- Success, failure and partial failure each have a specific message saying what happened and what to do next. No generic "Something went wrong".
- Long operations show progress and can be left and returned to.
- Destructive actions confirm once, stating exactly what is lost and what is kept. Offer undo where possible.

## Forms

- Labels above fields, never placeholder-only. Validate on blur, show the error next to the field, keep what the user typed.
- Sensible defaults filled in. Optional fields marked. Advanced options collapsed.
- The submit button states the outcome ("Connect account", not "Submit").

## States

Every view has designed loading (skeletons matching the final layout), empty (what this is, why it's empty, one action), error, and partial-data states.

## Copy

Plain words, sentence case, no jargon, no exclamation marks, no filler. Name things the way the user would.

## Consistency

Same component for the same job everywhere. Same word for the same thing everywhere. Check existing screens before inventing a pattern.

## Proof required in your report

- Screenshots at 360, 768 and 1280 px for every screen and state, saved under frontend/test-results/review/, inspected by you, with what you fixed listed per screen.
- The user-goal sentence and click count for each main task.
- Zero serious or critical accessibility violations.
