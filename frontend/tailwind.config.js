/** @type {import('tailwindcss').Config} */
const c = (name) => `rgb(var(--${name}) / <alpha-value>)`;
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    // These two replace Tailwind's defaults outright: a size or radius outside the system does not exist.
    // 8 for inputs and small controls, 12 for buttons and menus, 16 for cards and dialogs, full for pills.
    borderRadius: {
      none: "0",
      sm: "var(--radius-sm)",
      md: "var(--radius-md)",
      lg: "var(--radius-lg)",
      full: "9999px",
    },
    // Type scale 12/16, 14/20, 16/24, 20/28, 24/32. Nothing else.
    fontSize: {
      xs: ["var(--text-xs)", { lineHeight: "var(--text-xs-leading)" }],
      sm: ["var(--text-sm)", { lineHeight: "var(--text-sm-leading)" }],
      base: ["var(--text-base)", { lineHeight: "var(--text-base-leading)" }],
      xl: ["var(--text-xl)", { lineHeight: "var(--text-xl-leading)" }],
      "2xl": ["var(--text-2xl)", { lineHeight: "var(--text-2xl-leading)" }],
      // The hero metric only (docs/DESIGN.md, Typography). Nothing else uses it.
      display: ["var(--text-display)", { lineHeight: "var(--text-display-leading)" }],
    },
    container: {
      center: true,
      padding: "2rem",
      screens: { "2xl": "1400px" },
    },
    extend: {
      // Semantic names only (docs/DESIGN.md). Each maps to a CSS variable that changes with the theme.
      colors: {
        background: c("background"),
        surface: { DEFAULT: c("surface"), muted: c("surface-muted") },
        border: { DEFAULT: c("border"), strong: c("border-strong") },
        input: c("input"),
        ring: c("ring"),
        foreground: c("foreground"),
        "muted-foreground": c("muted-foreground"),
        subtle: c("subtle"),
        overlay: c("overlay"),
        accent: { DEFAULT: c("accent"), soft: c("accent-soft"), foreground: c("accent-foreground") },
        brand: { text: c("brand-text"), "text-muted": c("brand-text-muted"), accent: c("brand-accent"), from: c("brand-from"), to: c("brand-to") },
        primary: {
          DEFAULT: c("primary"),
          ink: c("primary-ink"),
          hover: c("primary-hover"),
          foreground: c("primary-foreground"),
          soft: c("primary-soft"),
          "soft-foreground": c("primary-soft-foreground"),
        },
        ...Object.fromEntries(
          ["success", "warning", "danger", "info"].map((name) => [
            name,
            { DEFAULT: c(name), soft: c(`${name}-soft`), foreground: c(`${name}-foreground`) },
          ]),
        ),
      },
      // The 4px grid.
      spacing: Object.fromEntries([0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 16].map((step) => [step, `var(--space-${step})`])),
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', "ui-sans-serif", "system-ui", "sans-serif"],
      },
      // Shadow only on floating layers; in dark it is "none" and the layer's border carries the edge.
      boxShadow: {
        float: "var(--shadow-float)",
        raised: "var(--shadow-raised)",
      },
      // The brand gradient, for brand moments only.
      backgroundImage: { brand: "var(--gradient-brand)" },
      transitionTimingFunction: { DEFAULT: "var(--ease)" },
      transitionDuration: { DEFAULT: "150ms" },
      keyframes: {
        rise: { from: { opacity: "0", transform: "translateY(8px)" }, to: { opacity: "1", transform: "none" } },
        "pulse-ring": { "0%": { boxShadow: "0 0 0 0 rgb(var(--success) / 0.45)" }, "70%, 100%": { boxShadow: "0 0 0 6px rgb(var(--success) / 0)" } },
        pop: { "0%": { opacity: "0", transform: "scale(0.85)" }, "60%": { opacity: "1", transform: "scale(1.04)" }, "100%": { transform: "scale(1)" } },
        draw: { from: { strokeDashoffset: "1" }, to: { strokeDashoffset: "0" } },
        float: { "0%, 100%": { transform: "translateY(0)" }, "50%": { transform: "translateY(-4px)" } },
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
        "fade-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        rise: "rise 200ms ease-out both",
        "pulse-ring": "pulse-ring 2s ease-out infinite",
        pop: "pop 400ms ease-out both",
        draw: "draw 700ms ease-out both",
        float: "float 4s ease-in-out infinite",
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        "fade-in": "fade-in 0.3s ease-out",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
