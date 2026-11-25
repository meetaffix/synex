// Measures WCAG 2.x contrast for every text and boundary pair the design system uses, in both themes, from the
// tokens in src/index.css. Run: npm run contrast  (add --markdown for the table in docs/DESIGN.md).
// Exits 1 when a text pair is under 4.5:1 or a boundary pair under 3:1.
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../src/index.css", import.meta.url), "utf8");

function block(selector) {
  const start = css.indexOf(`${selector} {`);
  const body = css.slice(start, css.indexOf("\n  }", start));
  const tokens = {};
  for (const [, name, r, g, b] of body.matchAll(/--([\w-]+):\s*(\d+)\s+(\d+)\s+(\d+)\s*;/g)) tokens[name] = [r, g, b].map(Number);
  return tokens;
}

const light = block(":root");
const themes = { light, dark: { ...light, ...block(".dark") } };

const lum = (rgb) => {
  const [r, g, b] = rgb.map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const ratio = (a, b) => {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};
const hex = (rgb) => `#${rgb.map((v) => v.toString(16).padStart(2, "0")).join("").toUpperCase()}`;

// [foreground token, background token, what it is, minimum]
const pairs = [
  ["foreground", "background", "Body text on the page", 4.5],
  ["foreground", "surface", "Body text on cards, dialogs, menus", 4.5],
  ["foreground", "surface-muted", "Text on muted surfaces and hovered rows", 4.5],
  ["muted-foreground", "background", "Muted text on the page", 4.5],
  ["muted-foreground", "surface", "Muted text on cards", 4.5],
  ["muted-foreground", "surface-muted", "Muted text on muted surfaces", 4.5],
  ["subtle", "background", "Subtle text on the page", 4.5],
  ["subtle", "surface", "Subtle text and placeholders on cards and fields", 4.5],
  ["subtle", "surface-muted", "Subtle text on muted surfaces", 4.5],
  ["primary-foreground", "primary", "Primary button label", 4.5],
  ["primary-foreground", "primary-hover", "Primary button label, hovered", 4.5],
  ["primary-ink", "background", "Links on the page", 4.5],
  ["primary-ink", "surface", "Links on cards", 4.5],
  ["primary-soft-foreground", "primary-soft", "Active sidebar item, primary pill, empty-state icon", 4.5],
  ["background", "foreground", "Tooltip text", 4.5],
  ...["success", "warning", "danger", "info"].flatMap((name) => [
    [name, `${name}-soft`, `${name} pill and message on its tint`, 4.5],
    [name, "surface", `${name} text on cards`, 4.5],
    [name, "background", `${name} text on the page`, 4.5],
    [`${name}-foreground`, name, `Text on solid ${name}`, 4.5],
  ]),
  ["accent", "background", "Accent text on the page", 4.5],
  ["accent", "surface", "Accent text on cards", 4.5],
  ["accent", "accent-soft", "Accent on its tint", 4.5],
  ["accent-foreground", "accent", "Text on solid accent", 4.5],
  // Text on the brand gradient is measured on both of its stops (the colour between them is never darker than the lighter stop, nor lighter than the darker).
  ["brand-text", "brand-from", "Gradient text, start stop", 4.5],
  ["brand-text", "brand-to", "Gradient text, end stop", 4.5],
  ["brand-text-muted", "brand-from", "Gradient secondary text, start stop", 4.5],
  ["brand-text-muted", "brand-to", "Gradient secondary text, end stop", 4.5],
  ["brand-accent", "brand-from", "Gradient warm highlight, start stop", 4.5],
  ["brand-accent", "brand-to", "Gradient warm highlight, end stop", 4.5],
  ["input", "background", "Field and control boundary on the page", 3],
  ["input", "surface", "Field and control boundary on cards", 3],
  ["ring", "background", "Focus ring on the page", 3],
  ["ring", "surface", "Focus ring on cards", 3],
  ["ring", "surface-muted", "Focus ring on muted surfaces", 3],
  ["primary", "background", "Primary button edge on the page", 3],
  ["primary", "surface", "Primary button and checked control on cards", 3],
  ["surface", "input", "Switch thumb on the off track", 3],
  ["surface", "primary", "Switch thumb and radio dot on the on track", 3],
];

const markdown = process.argv.includes("--markdown");
let failed = 0;
if (markdown) console.log("| Pair | Use | Light | Dark | Minimum |\n|---|---|---|---|---|");
for (const [fg, bg, use, min] of pairs) {
  const cells = Object.entries(themes).map(([theme, t]) => {
    if (!t[fg] || !t[bg]) throw new Error(`missing token ${fg} or ${bg} in ${theme}`);
    const value = ratio(t[fg], t[bg]);
    if (value < min) failed++;
    return { theme, value, fg: hex(t[fg]), bg: hex(t[bg]) };
  });
  if (markdown) {
    const cell = (c) => `${c.value.toFixed(2)}:1 (${c.fg} on ${c.bg})${c.value < min ? " FAIL" : ""}`;
    console.log(`| ${fg} on ${bg} | ${use} | ${cell(cells[0])} | ${cell(cells[1])} | ${min}:1 |`);
  } else {
    for (const c of cells) {
      console.log(`${c.value >= min ? "PASS" : "FAIL"}  ${c.value.toFixed(2).padStart(5)}:1  (min ${min})  ${c.theme.padEnd(5)}  ${fg} on ${bg}  ${c.fg} on ${c.bg}`);
    }
  }
}
if (!markdown) console.log(failed ? `\n${failed} pair(s) below the minimum.` : `\nAll ${pairs.length * 2} pairs pass.`);
process.exit(failed ? 1 : 0);
