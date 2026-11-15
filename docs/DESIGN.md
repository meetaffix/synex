# Synex design system

This is the single design reference for Synex. Tokens live in `frontend/src/index.css`, the Tailwind names that use them in `frontend/tailwind.config.js`, the primitives in `frontend/src/components/ui`, and every token and component is rendered at `/design` in development.

## Direction

- **Feel:** warm, confident, alive. Soft and rounded, with generous spacing, and a sense of momentum: a person should feel their pipeline growing. Never corporate grey, never loud. The level of craft is that of Linear, Attio, Mercury and Raycast; none of their looks is copied.
- **Themes:** light and dark, the person's choice. The default follows the device. The choice is in the user menu (Theme: Match my device, Light, Dark) and is remembered for each person.
- **Brand colour:** teal-green.

## Colour tokens

Semantic names only. Components never use a raw colour; each name below is a CSS variable that changes with the theme, and Tailwind exposes it under the same name (`bg-surface`, `text-muted-foreground`, `border-input`, `bg-success-soft`, and so on). Values are stored as `R G B` triplets so Tailwind's opacity modifiers work (`bg-primary/40`).

| Token | Tailwind | Light | Dark | Used for |
|---|---|---|---|---|
| background | `bg-background` | #F6F8F7 | #0E1513 | The page |
| surface | `bg-surface` | #FFFFFF | #151E1B | Cards, dialogs, menus, sidebar, fields |
| surface-muted | `bg-surface-muted` | #EEF3F1 | #1B2623 | Hover rows, secondary fills, skeletons |
| border | `border-border` | #E3E9E6 | #25322E | Card edges, dividers |
| border-strong | `border-border-strong` | #C9D4CF | #34443F | Table header rule, secondary button edge |
| input | `border-input` | #7A8B85 | #5F756F | Field and control boundaries (added, see below) |
| text | `text-foreground` | #12201C | #E8EFEC | Body text |
| text-muted | `text-muted-foreground` | #51625C | #9DB0A9 | Descriptions, labels of secondary weight |
| text-subtle | `text-subtle` | #5E6F69 | #7F928B | Placeholders, captions (light value changed, see below) |
| primary | `bg-primary`, `text-primary` | #0F766E | #2DD4BF | Primary button, links, checked controls |
| primary-hover | `bg-primary-hover` | #0B5F59 | #5EEAD4 | Primary button hover |
| primary-foreground | `text-primary-foreground` | #FFFFFF | #06201C | Text on primary |
| primary-soft | `bg-primary-soft` | #E3F4F1 | #12332E | Active sidebar item, empty-state icon circle |
| primary-soft-foreground | `text-primary-soft-foreground` | #0B5F59 | #7FE7D8 | Text on primary-soft |
| success / success-soft | `text-success`, `bg-success-soft` | #166534 on #E7F6EC | #6EE7A0 on #12301F | Positive states (light value changed) |
| warning / warning-soft | `text-warning`, `bg-warning-soft` | #B45309 on #FEF3E2 | #FBBF4D on #3A2A0F | Needs attention |
| danger / danger-soft | `text-danger`, `bg-danger-soft` | #B91C1C on #FDECEC | #FCA5A5 on #3B1618 | Errors, destructive actions |
| info / info-soft | `text-info`, `bg-info-soft` | #1D4ED8 on #E8EFFD | #9DBBFD on #14264A | Neutral notices |
| *-foreground (solid) | `text-success-foreground` … | #FFFFFF | dark tint of each hue | Text on a solid status fill |
| accent / accent-soft | `text-accent`, `bg-accent-soft` | #B5442F on #FCEBE6 | #FFA38D on #3A1E19 | The warm accent paired with teal: highlights, illustrations, the one number that matters most. Used sparingly. |
| accent-foreground | `text-accent-foreground` | #FFFFFF | #280E08 | Text on a solid accent fill |
| brand-from / brand-to | `bg-brand` (gradient) | #0F766E to #0A4D49 | #0F3D38 to #0A1F1C | The brand gradient, brand moments only (see Gradients) |
| brand-text, brand-text-muted, brand-accent | `text-brand-text` … | #FFFFFF, #D5F2EE, #FFE6DC | #E8EFEC, #A9C4BD, #FFC2B3 | Text and the warm highlight placed on the gradient |
| ring | `ring-ring` | #0F766E | #2DD4BF | Focus ring, 2px with 2px offset |
| overlay | `bg-overlay/40` | #12201C | #000000 | Dialog and sheet backdrop at 40% |

### Where the final values differ from the starting values, and why

- **text-subtle, light: #6B7C76 → #5E6F69.** The starting value measured 4.13:1 on background, 4.40:1 on surface and 3.93:1 on surface-muted, all under 4.5:1. #5E6F69 measures 4.98, 5.31 and 4.74.
- **success, light: #15803D → #166534.** On its tint (#E7F6EC) the starting value measured 4.49:1. #166534 measures 6.38:1.
- **input (new token).** border-strong (#C9D4CF) is 1.43:1 against the page and 1.52:1 against a card, too faint to be the visible edge of a field or checkbox (WCAG 1.4.11 needs 3:1). Fields, selects, checkboxes, radios and the switch track use `input`: #7A8B85 light (3.36:1 on background, 3.58:1 on surface), #5F756F dark (3.75:1 and 3.45:1). border and border-strong stay for decorative lines.
- **Dark status colours** were not given; they were chosen as light foregrounds on dark tints of the same hue: success #6EE7A0 on #12301F, warning #FBBF4D on #3A2A0F, danger #FCA5A5 on #3B1618, info #9DBBFD on #14264A. Each solid status also has a dark foreground for text placed on it.
- Everything else is the starting value unchanged.

### Contrast

Every pair below is measured from the tokens by `npm run contrast` (in `frontend/`), which exits with an error if any pair drops below its minimum. Text needs 4.5:1; boundaries and focus indicators need 3:1.

| Pair | Use | Light | Dark | Minimum |
|---|---|---|---|---|
| foreground on background | Body text on the page | 15.76:1 (#12201C on #F6F8F7) | 15.84:1 (#E8EFEC on #0E1513) | 4.5:1 |
| foreground on surface | Body text on cards, dialogs, menus | 16.81:1 (#12201C on #FFFFFF) | 14.58:1 (#E8EFEC on #151E1B) | 4.5:1 |
| foreground on surface-muted | Text on muted surfaces and hovered rows | 14.99:1 (#12201C on #EEF3F1) | 13.34:1 (#E8EFEC on #1B2623) | 4.5:1 |
| muted-foreground on background | Muted text on the page | 6.06:1 (#51625C on #F6F8F7) | 8.12:1 (#9DB0A9 on #0E1513) | 4.5:1 |
| muted-foreground on surface | Muted text on cards | 6.46:1 (#51625C on #FFFFFF) | 7.47:1 (#9DB0A9 on #151E1B) | 4.5:1 |
| muted-foreground on surface-muted | Muted text on muted surfaces | 5.76:1 (#51625C on #EEF3F1) | 6.84:1 (#9DB0A9 on #1B2623) | 4.5:1 |
| subtle on background | Subtle text on the page | 4.98:1 (#5E6F69 on #F6F8F7) | 5.63:1 (#7F928B on #0E1513) | 4.5:1 |
| subtle on surface | Subtle text and placeholders on cards and fields | 5.31:1 (#5E6F69 on #FFFFFF) | 5.18:1 (#7F928B on #151E1B) | 4.5:1 |
| subtle on surface-muted | Subtle text on muted surfaces | 4.74:1 (#5E6F69 on #EEF3F1) | 4.74:1 (#7F928B on #1B2623) | 4.5:1 |
| primary-foreground on primary | Primary button label | 5.47:1 (#FFFFFF on #0F766E) | 9.16:1 (#06201C on #2DD4BF) | 4.5:1 |
| primary-foreground on primary-hover | Primary button label, hovered | 7.51:1 (#FFFFFF on #0B5F59) | 11.53:1 (#06201C on #5EEAD4) | 4.5:1 |
| primary on background | Links on the page | 5.13:1 (#0F766E on #F6F8F7) | 9.94:1 (#2DD4BF on #0E1513) | 4.5:1 |
| primary on surface | Links on cards | 5.47:1 (#0F766E on #FFFFFF) | 9.15:1 (#2DD4BF on #151E1B) | 4.5:1 |
| primary-soft-foreground on primary-soft | Active sidebar item, primary pill, empty-state icon | 6.61:1 (#0B5F59 on #E3F4F1) | 9.31:1 (#7FE7D8 on #12332E) | 4.5:1 |
| background on foreground | Tooltip text | 15.76:1 (#F6F8F7 on #12201C) | 15.84:1 (#0E1513 on #E8EFEC) | 4.5:1 |
| success on success-soft | success pill and message on its tint | 6.38:1 (#166534 on #E7F6EC) | 9.26:1 (#6EE7A0 on #12301F) | 4.5:1 |
| success on surface | success text on cards | 7.13:1 (#166534 on #FFFFFF) | 11.03:1 (#6EE7A0 on #151E1B) | 4.5:1 |
| success on background | success text on the page | 6.69:1 (#166534 on #F6F8F7) | 11.98:1 (#6EE7A0 on #0E1513) | 4.5:1 |
| success-foreground on success | Text on solid success | 7.13:1 (#FFFFFF on #166534) | 11.12:1 (#062012 on #6EE7A0) | 4.5:1 |
| warning on warning-soft | warning pill and message on its tint | 4.58:1 (#B45309 on #FEF3E2) | 8.34:1 (#FBBF4D on #3A2A0F) | 4.5:1 |
| warning on surface | warning text on cards | 5.02:1 (#B45309 on #FFFFFF) | 10.27:1 (#FBBF4D on #151E1B) | 4.5:1 |
| warning on background | warning text on the page | 4.71:1 (#B45309 on #F6F8F7) | 11.15:1 (#FBBF4D on #0E1513) | 4.5:1 |
| warning-foreground on warning | Text on solid warning | 5.02:1 (#FFFFFF on #B45309) | 10.49:1 (#241804 on #FBBF4D) | 4.5:1 |
| danger on danger-soft | danger pill and message on its tint | 5.66:1 (#B91C1C on #FDECEC) | 8.42:1 (#FCA5A5 on #3B1618) | 4.5:1 |
| danger on surface | danger text on cards | 6.47:1 (#B91C1C on #FFFFFF) | 8.97:1 (#FCA5A5 on #151E1B) | 4.5:1 |
| danger on background | danger text on the page | 6.07:1 (#B91C1C on #F6F8F7) | 9.75:1 (#FCA5A5 on #0E1513) | 4.5:1 |
| danger-foreground on danger | Text on solid danger | 6.47:1 (#FFFFFF on #B91C1C) | 9.71:1 (#280A0C on #FCA5A5) | 4.5:1 |
| info on info-soft | info pill and message on its tint | 5.81:1 (#1D4ED8 on #E8EFFD) | 7.80:1 (#9DBBFD on #14264A) | 4.5:1 |
| info on surface | info text on cards | 6.70:1 (#1D4ED8 on #FFFFFF) | 8.89:1 (#9DBBFD on #151E1B) | 4.5:1 |
| info on background | info text on the page | 6.28:1 (#1D4ED8 on #F6F8F7) | 9.65:1 (#9DBBFD on #0E1513) | 4.5:1 |
| info-foreground on info | Text on solid info | 6.70:1 (#FFFFFF on #1D4ED8) | 9.53:1 (#08142E on #9DBBFD) | 4.5:1 |
| accent on background | Accent text on the page | 5.14:1 (#B5442F on #F6F8F7) | 9.58:1 (#FFA38D on #0E1513) | 4.5:1 |
| accent on surface | Accent text on cards | 5.48:1 (#B5442F on #FFFFFF) | 8.82:1 (#FFA38D on #151E1B) | 4.5:1 |
| accent on accent-soft | Accent on its tint | 4.74:1 (#B5442F on #FCEBE6) | 7.88:1 (#FFA38D on #3A1E19) | 4.5:1 |
| accent-foreground on accent | Text on solid accent | 5.48:1 (#FFFFFF on #B5442F) | 9.40:1 (#280E08 on #FFA38D) | 4.5:1 |
| brand-text on brand-from | Gradient text, start stop | 5.47:1 (#FFFFFF on #0F766E) | 10.31:1 (#E8EFEC on #0F3D38) | 4.5:1 |
| brand-text on brand-to | Gradient text, end stop | 9.67:1 (#FFFFFF on #0A4D49) | 14.68:1 (#E8EFEC on #0A1F1C) | 4.5:1 |
| brand-text-muted on brand-from | Gradient secondary text, start stop | 4.63:1 (#D5F2EE on #0F766E) | 6.49:1 (#A9C4BD on #0F3D38) | 4.5:1 |
| brand-text-muted on brand-to | Gradient secondary text, end stop | 8.18:1 (#D5F2EE on #0A4D49) | 9.23:1 (#A9C4BD on #0A1F1C) | 4.5:1 |
| brand-accent on brand-from | Gradient warm highlight, start stop | 4.59:1 (#FFE6DC on #0F766E) | 7.81:1 (#FFC2B3 on #0F3D38) | 4.5:1 |
| brand-accent on brand-to | Gradient warm highlight, end stop | 8.11:1 (#FFE6DC on #0A4D49) | 11.11:1 (#FFC2B3 on #0A1F1C) | 4.5:1 |
| input on background | Field and control boundary on the page | 3.36:1 (#7A8B85 on #F6F8F7) | 3.75:1 (#5F756F on #0E1513) | 3:1 |
| input on surface | Field and control boundary on cards | 3.58:1 (#7A8B85 on #FFFFFF) | 3.45:1 (#5F756F on #151E1B) | 3:1 |
| ring on background | Focus ring on the page | 5.13:1 (#0F766E on #F6F8F7) | 9.94:1 (#2DD4BF on #0E1513) | 3:1 |
| ring on surface | Focus ring on cards | 5.47:1 (#0F766E on #FFFFFF) | 9.15:1 (#2DD4BF on #151E1B) | 3:1 |
| ring on surface-muted | Focus ring on muted surfaces | 4.88:1 (#0F766E on #EEF3F1) | 8.37:1 (#2DD4BF on #1B2623) | 3:1 |
| primary on background | Primary button edge on the page | 5.13:1 (#0F766E on #F6F8F7) | 9.94:1 (#2DD4BF on #0E1513) | 3:1 |
| primary on surface | Primary button and checked control on cards | 5.47:1 (#0F766E on #FFFFFF) | 9.15:1 (#2DD4BF on #151E1B) | 3:1 |
| surface on input | Switch thumb on the off track | 3.58:1 (#FFFFFF on #7A8B85) | 3.45:1 (#151E1B on #5F756F) | 3:1 |
| surface on primary | Switch thumb and radio dot on the on track | 5.47:1 (#FFFFFF on #0F766E) | 9.15:1 (#151E1B on #2DD4BF) | 3:1 |

### Gradients

Gradients are allowed in **brand moments only**: the sign-in brand panel and phone header band, the welcome screen, the hero metric (reply rate), and the campaign-launch celebration (the celebration pattern exists as the success illustration; the app has no campaign-launch screen yet, so it is not wired there). They run soft teal to deep green (`bg-brand`), with the warm accent as a highlight inside them. **Never** on buttons, inputs, table rows or ordinary cards. Also allowed because they are data or craft rather than decoration: the fill under the performance chart line, the sparkline fills, the logo mark's tile and the skeleton shimmer. Text on a gradient is measured on both of its stops (see the contrast table).

### Depth

- **Light:** raised cards (metric cards, account cards, the attention and activity panels, the hero) carry a soft layered shadow (`shadow-raised`). Floating layers (menus, dialogs, tooltips) keep `shadow-float`.
- **Dark:** shadows are replaced by borders, plus a subtle highlight along the top edge of raised cards (`shadow-raised` is `inset 0 1px 0` at 7% white in dark).

### Rules

- Every text and background pair meets 4.5:1. Text 24px and larger, UI boundaries and focus rings meet 3:1.
- Status never relies on colour alone: a status pill always carries its label, and errors carry words ("Test failed.", the field's message).
- Dark is designed, not inverted. Surfaces get lighter as they rise (background #0E1513, surface #151E1B, surface-muted #1B2623), and shadows are replaced by borders (`--shadow-float` is `none` in dark; every floating layer has a 1px border).

## Brand

- **Logo:** `components/brand/Logo.tsx`. A rounded tile on the brand gradient holding a rising path that joins two profiles (the second, warm one is the person reached). It draws identically in both themes. The wordmark is set in Plus Jakarta Sans 700 as SVG text, so it uses the bundled font rather than a separate asset.
- **Illustrations:** `components/brand/Illustration.tsx`, one set in one style: a 160×120 canvas, 2px rounded primary strokes, shapes filled with primary-soft or surface, one warm accent detail per picture, all drawn from tokens so both themes work. Names: accounts, campaigns, inbox, leads, lists, templates, onboarding, success, error. They are decorative (`aria-hidden`); the words beside them carry the meaning. No stock imagery and no emoji.
- **Name:** the product is "Synex" in every sentence and as the page title.

## Typography

- **Family:** Plus Jakarta Sans for everything, bundled with the app from `@fontsource/plus-jakarta-sans` (weights 400, 500, 600, 700, latin). No runtime request to a font CDN.
- **Figures:** tabular numerals everywhere (`font-variant-numeric: tabular-nums` on `body`), so columns of numbers line up.
- **Scale (size/line height), nothing else:** 12/16 `text-xs`, 14/20 `text-sm`, 16/24 `text-base`, 20/28 `text-xl`, 24/32 `text-2xl`. Tailwind's other sizes are removed from the theme, so an off-scale size does not build.

| Role | Style |
|---|---|
| Page title | 24/32, 600 (`text-2xl font-semibold`) |
| Dialog title | 20/28, 600 (`text-xl font-semibold`) |
| Section title | 16/24, 600 (`text-base font-semibold`) |
| Body | 14/20, 400 (`text-sm`) |
| Label | 14/20, 500 (`text-sm font-medium`) |
| Caption, table header | 12/16, 500 (`text-xs font-medium`) |

## Shape and space

- **Spacing:** the 4px grid, used as 4, 8, 12, 16, 24, 32, 48 (`1, 2, 3, 4, 6, 8, 12`).
- **Radius:** 8 for inputs and small controls (`rounded-sm`), 12 for buttons and menus (`rounded-md`), 16 for cards and dialogs (`rounded-lg`), full for pills, avatars, status dots and the primary button (`rounded-full`). No other radius exists in the theme.
- **Cards:** surface colour, 1px border, 16 radius, 24 padding (16 on phones where a card sits edge to edge). No shadow.
- **Shadow:** only on floating layers (menus, dialogs, sheets, tooltips, toasts): `shadow-float`, soft and low. None in dark.
- **Page:** gutters 32 on desktop, 16 on phones. Content max width 1280.
- **Controls:** 40px tall, 36px compact in dense tables, at least 44px on phones (buttons, fields, selects and sidebar items grow to 44 below 640px).
- **Page structure:** title, one-line description, primary action, then content; 24 between the header and the content.

## Components

Every component has default, hover, focus, active, disabled and (where it can wait) loading states, in light and dark. Focus is always the 2px ring with a 2px offset. Disabled is the same component at half strength, never hidden.

| Component | Anatomy and sizes | States |
|---|---|---|
| **Button: primary** | Filled teal pill, 600 weight, 40 tall (44 on phones), 20 side padding. One per view. | Hover primary-hover; active scales to 98%; disabled 50%; loading shows a spinner and keeps the label, and cannot be pressed twice. |
| **Button: secondary** | Surface fill, border-strong edge, 12 radius, 500 weight. | Hover surface-muted. |
| **Button: ghost** | No fill, 12 radius. For tertiary actions and icon buttons. | Hover surface-muted. |
| **Button: danger** | Danger text on danger-soft with a danger edge. Destructive actions are never primary. | Hover strengthens the edge. |
| **Input, textarea** | Label above (14/500), field 40 tall, 8 radius, input-colour border, surface fill, placeholder in text-subtle, help or error below (12). | Focus ring; invalid has a danger border and the message below; disabled sits on surface-muted. |
| **Select** | Same box as the input with a chevron. Native select where the browser's list is enough; the Radix select where items need styling. | Open list is a menu (12 radius, float shadow). |
| **Checkbox** | 20px box, 8 radius, input border; checked fills primary with a white tick. | Indeterminate shows a dash. |
| **Radio** | 20px circle, input border; checked shows a primary dot inside a surface ring. Native input, so arrow keys work. | Disabled 50%. |
| **Switch** | 44×24 pill track, 20px thumb. Off track uses input, on track primary. Announced as a switch. | Changes take effect at once. |
| **Badge, status pill** | Full radius, 12/500, soft tint background with matching foreground, a small dot, and the label. Variants: primary, success, warning, danger, info, neutral. | Static. |
| **Card** | Surface, 1px border, 16 radius, 24 padding; header title 16/600, description 14 muted. | Static; clickable cards get the hover row colour. |
| **Table** | Sticky header row (12/500, muted, border-strong rule), rows 56 tall, row hover surface-muted, numbers right-aligned, sortable column headers (`aria-sort`). A table with more columns than the essentials has a Columns menu (remembered for each person); the essentials always show first, and the table scrolls sideways inside its labelled, focusable region when the chosen columns are wider than the page. | Selected rows use primary-soft. |
| **Form field** | `FormField`: label above (14/500, "(optional)" when optional), the field, then help or the error (12) linked by `aria-describedby`. Forms validate on blur and keep what was typed. | Invalid sets `aria-invalid` and a danger border. |
| **Tabs** | Text tabs with a 2px primary underline on the active one. | Hover text colour; focus ring. |
| **Dialog** | Surface, 16 radius, 24 padding, 1px border, float shadow, 40% overlay. Title 20/600, description 14 muted, actions bottom right. Focus is trapped and returns to the opener. | Opens in 200ms; Escape closes. |
| **Sheet** | Surface panel from the left, border on its edge, used for navigation on phones and tablets. | Slides in 200ms; Escape closes. |
| **Dropdown menu** | Surface, 12 radius, 1px border, float shadow, 4 padding, items 36 tall with 8 radius. Not modal: Escape and an outside click close it and focus returns to its trigger. | Item hover and focus surface-muted; destructive items in danger. |
| **Tooltip** | Text inverted (background on foreground), 8 radius, 12/500, max 320 wide. | Appears after 200ms. |
| **Toast** | Surface, 16 radius, border, float shadow, bottom right, with a close button. Follows the theme. | Success and error carry their words. |
| **Empty state** | A drawn illustration from the brand set (or an icon in a primary-soft circle where no illustration is assigned yet), a one-line title (16/600), one line of explanation (14 muted), one primary action. | |
| **Hero metric** | The single most important number on a screen, on the brand gradient: label 14, value 48/700 in `brand-accent`, a plain-words change and a sparkline. Counts up once when it first appears. | Shows "Not available yet" rather than a made-up number. |
| **Sparkline, change indicator** | A 72×32 trend line with a faint fill; beside it an arrow and the change in words ("+3 vs previous week"). Colour never carries the change alone. Neither shows without at least two real periods of data. | |
| **Progress ring** | 64px ring with "done/total" in the middle and `aria-label="2 of 4 steps done"`. | The ring fills over 700ms. |
| **Avatar stack and name-derived avatar** | Initials on one of five measured tint pairs (primary, info, accent, success, warning), chosen from the name so a person always has the same colour. Stacks overlap by 8px with a surface ring. | |
| **Command palette** | Ctrl or Cmd + K. A dialog with a search field and grouped results (pages, campaigns, sender accounts, leads), arrow keys and Enter. | |
| **Skeleton** | surface-muted blocks in the shape of the final layout, 8 radius, pulsing (still under reduced motion). | |
| **Avatar** | Full radius; initials on primary-soft when there is no picture. | |
| **Page header** | Title 24/600, one-line description 14 muted, primary action on the right (below on phones). | |
| **Sidebar item** | 40 tall (44 on phones), 12 radius, icon and label 14/500, muted text. The active item is primary-soft with primary-soft-foreground text. | Hover surface-muted. |
| **Sidebar** | Surface with a border on its right edge (not a dark slab). | Collapses to icons on desktop. |
| **Metric card** | A card with a 14 muted label and a 24/600 tabular value; "Not available yet" in 14 muted when there is no data. | Loading shows a skeleton the size of the value. |
| **Filter bar** | Labelled fields in a row (wrapping on phones), 16 apart, above the content they filter. | |

## Motion and reward

- 150ms ease-out for hovers and presses; 200ms for dialogs, sheets, menus and page transitions.
- Pages and panels fade and rise into place in 200ms (`animate-rise`); list items stagger in 45ms apart, up to ten. Numbers count up the first time they appear (`useCountUp`, 700ms). Clickable cards lift 2px on hover. A running campaign's status dot pulses gently. Skeletons shimmer softly.
- Success moments are short and tasteful: connecting an account shows the success illustration (the check draws itself) with the next step. No confetti.
- All of it is decoration: none of it carries meaning, and `prefers-reduced-motion: reduce` turns it off (animations and transitions run for 1ms, counts show the final number at once).

## Voice

Plain, warm, short. Sentence case. No exclamation marks, no jargon, no emoji. Name things the way the person would ("Sender accounts", "Connect account", "Daily action limit"). Every message says what happened and what to do next.

## Do and don't

| Don't | Why |
|---|---|
| Gradients outside brand moments | On buttons, inputs, table rows and ordinary cards they fight the calm surfaces and make hierarchy unclear. They are for the sign-in panel, the welcome screen, the hero metric and the launch celebration. |
| Glows and coloured shadows | Shadows are for floating layers only, and none in dark. |
| A dark slab sidebar | It splits the page in two and does not work in both themes; the sidebar is a surface with a border. |
| Boxes inside boxes | Group with space; a card holds content, not more cards. |
| More than one primary action per view | The primary pill marks the one thing to do next. |
| Text under 12px | It is unreadable for many people and outside the scale. |
| Placeholder-only labels | The label disappears when typing starts; every field has a label above it. |
| Raw hex in components | Colours come from tokens so both themes stay right. |

## Known debt

- **Content publishing pages use class-based CSS, not the component library.** Overview, Studio, Calendar, Queue, Activity, Analytics, Connections, publishing Settings and the browser-extension page keep their own class names (`post-row`, `editor-panel`, `calendar-grid`, `settings-grid` and so on), styled in the "Content publishing pages" block of `frontend/src/index.css`. Every rule there uses the tokens and the type scale, so the pages follow both themes, and their headers, empty states, notices, loading states and status pills already come from the shared components. What remains is to rebuild the page bodies on `Card`, `Table`, `FormField` and the primitives, then delete that block. Until then, a change to a token is checked on these pages as well.
- The sign-in pages (login, register, forgot and reset password) were rebuilt on the shared components and have no page CSS left.

## Theme switching

- `index.html` applies the stored theme before the first paint (no flash of the wrong theme), reading `synex.theme` from local storage. Without a stored choice it follows `prefers-color-scheme`.
- `src/lib/theme.ts` owns the rules. The person's own choice is stored as `synex.theme.<user id>` and wins once they are signed in; the last choice in the browser is also stored as `synex.theme` for the next first paint. "Match my device" keeps following the system setting as it changes.
- The `dark` class on `<html>` swaps every token at once.
