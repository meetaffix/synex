import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export type IllustrationName = "accounts" | "campaigns" | "inbox" | "leads" | "lists" | "templates" | "onboarding" | "success" | "error";

/* One style for the whole set: a 160×120 canvas, 2px rounded strokes in primary, shapes filled with primary-soft or
   surface, and one warm accent detail per picture. Every colour is a token, so each drawing works in both themes. */

const LINE = "fill-none stroke-primary [stroke-linecap:round] [stroke-linejoin:round]";
const SOFT = "fill-primary-soft stroke-primary [stroke-linejoin:round]";
const PAPER = "fill-surface stroke-primary [stroke-linejoin:round]";
const WARM = "fill-accent stroke-accent";
const WARM_SOFT = "fill-accent-soft stroke-accent [stroke-linejoin:round]";

const drawings: Record<IllustrationName, ReactNode> = {
  accounts: (
    <>
      <ellipse cx="80" cy="106" rx="52" ry="5" className="fill-surface-muted" />
      <rect x="14" y="30" width="60" height="44" rx="10" strokeWidth="2" className={PAPER} />
      <circle cx="30" cy="46" r="7" strokeWidth="2" className={SOFT} />
      <path d="M26 62h22M26 68h14" strokeWidth="2" className={LINE} />
      <rect x="86" y="46" width="60" height="44" rx="10" strokeWidth="2" className={PAPER} />
      <circle cx="102" cy="62" r="7" strokeWidth="2" className={SOFT} />
      <path d="M98 78h22M98 84h14" strokeWidth="2" className={LINE} />
      <path d="M74 52c6 0 6 10 12 10" strokeWidth="2" strokeDasharray="3 4" className={LINE} />
      <circle cx="80" cy="56" r="10" strokeWidth="2" className={WARM_SOFT} />
      <path d="M75.5 56.5l3 3 6-6.5" strokeWidth="2" className="fill-none stroke-accent [stroke-linecap:round] [stroke-linejoin:round]" />
    </>
  ),
  campaigns: (
    <>
      <ellipse cx="80" cy="106" rx="52" ry="5" className="fill-surface-muted" />
      <path d="M18 88c20-4 28-30 48-34s34 6 52-18" strokeWidth="2" strokeDasharray="3 5" className={LINE} />
      <circle cx="18" cy="88" r="4" strokeWidth="2" className={SOFT} />
      <circle cx="44" cy="70" r="4" strokeWidth="2" className={SOFT} />
      <circle cx="78" cy="58" r="4" strokeWidth="2" className={SOFT} />
      <path d="M128 24l18-4-6 22-9-8-9 6 3-11z" strokeWidth="2" className={PAPER} />
      <path d="M137 34l9-14" strokeWidth="2" className={LINE} />
      <circle cx="108" cy="42" r="3" className={WARM} />
    </>
  ),
  inbox: (
    <>
      <ellipse cx="80" cy="106" rx="52" ry="5" className="fill-surface-muted" />
      <rect x="24" y="40" width="80" height="54" rx="10" strokeWidth="2" className={PAPER} />
      <path d="M28 46l36 26 36-26" strokeWidth="2" className={LINE} />
      <path d="M92 22h46a8 8 0 018 8v20a8 8 0 01-8 8h-22l-10 9v-9h-14a8 8 0 01-8-8V30a8 8 0 018-8z" strokeWidth="2" className={WARM_SOFT} />
      <path d="M100 34h38M100 44h24" strokeWidth="2" className="fill-none stroke-accent [stroke-linecap:round]" />
    </>
  ),
  leads: (
    <>
      <ellipse cx="80" cy="106" rx="52" ry="5" className="fill-surface-muted" />
      <circle cx="46" cy="48" r="11" strokeWidth="2" className={SOFT} />
      <path d="M26 92c0-14 9-22 20-22s20 8 20 22z" strokeWidth="2" className={SOFT} />
      <circle cx="114" cy="48" r="11" strokeWidth="2" className={SOFT} />
      <path d="M94 92c0-14 9-22 20-22s20 8 20 22z" strokeWidth="2" className={SOFT} />
      <circle cx="80" cy="40" r="13" strokeWidth="2" className={WARM_SOFT} />
      <path d="M58 94c0-17 10-27 22-27s22 10 22 27z" strokeWidth="2" className={WARM_SOFT} />
    </>
  ),
  lists: (
    <>
      <ellipse cx="80" cy="106" rx="52" ry="5" className="fill-surface-muted" />
      <rect x="30" y="22" width="100" height="24" rx="8" strokeWidth="2" className={SOFT} />
      <rect x="22" y="44" width="100" height="24" rx="8" strokeWidth="2" className={PAPER} />
      <rect x="38" y="66" width="100" height="24" rx="8" strokeWidth="2" className={PAPER} />
      <path d="M46 34h40M38 56h40M54 78h40" strokeWidth="2" className={LINE} />
      <path d="M108 74l5 5 9-10" strokeWidth="2" className="fill-none stroke-accent [stroke-linecap:round] [stroke-linejoin:round]" />
    </>
  ),
  templates: (
    <>
      <ellipse cx="80" cy="106" rx="52" ry="5" className="fill-surface-muted" />
      <path d="M44 16h46l26 26v54a6 6 0 01-6 6H44a6 6 0 01-6-6V22a6 6 0 016-6z" strokeWidth="2" className={PAPER} />
      <path d="M90 16v20a6 6 0 006 6h20" strokeWidth="2" className={SOFT} />
      <path d="M50 54h40M50 66h52M50 78h30" strokeWidth="2" className={LINE} />
      <path d="M118 66l8-8 6 6-8 8-9 3z" strokeWidth="2" className={WARM_SOFT} />
    </>
  ),
  onboarding: (
    <>
      <ellipse cx="80" cy="106" rx="56" ry="5" className="fill-surface-muted" />
      <path d="M20 96h30V76h30V56h30V36h20" strokeWidth="2" className={LINE} />
      <rect x="20" y="80" width="30" height="16" rx="4" strokeWidth="2" className={SOFT} />
      <rect x="50" y="60" width="30" height="36" rx="4" strokeWidth="2" className={SOFT} />
      <rect x="80" y="40" width="30" height="56" rx="4" strokeWidth="2" className={SOFT} />
      <path d="M118 36V14" strokeWidth="2" className={LINE} />
      <path d="M118 14h18l-5 7 5 7h-18z" strokeWidth="2" className={WARM_SOFT} />
    </>
  ),
  success: (
    <>
      <ellipse cx="80" cy="106" rx="44" ry="5" className="fill-surface-muted" />
      <circle cx="80" cy="56" r="34" strokeWidth="2" className={SOFT} />
      <circle cx="80" cy="56" r="25" strokeWidth="2" className={PAPER} />
      <path d="M68 57l9 9 17-19" pathLength={1} strokeDasharray="1" strokeWidth="3" className="animate-draw fill-none stroke-primary [stroke-linecap:round] [stroke-linejoin:round]" />
      <path d="M130 22v10M125 27h10M32 30v8M28 34h8" strokeWidth="2" className="fill-none stroke-accent [stroke-linecap:round]" />
      <circle cx="120" cy="86" r="3" className={WARM} />
    </>
  ),
  error: (
    <>
      <ellipse cx="80" cy="106" rx="52" ry="5" className="fill-surface-muted" />
      <rect x="20" y="42" width="48" height="26" rx="13" strokeWidth="2" className={SOFT} />
      <rect x="92" y="52" width="48" height="26" rx="13" strokeWidth="2" className={SOFT} />
      <path d="M60 55h16M84 65h16" strokeWidth="2" className={LINE} />
      <path d="M76 38l8 18-8 12 8 14" strokeWidth="2" className="fill-none stroke-accent [stroke-linecap:round] [stroke-linejoin:round]" />
      <circle cx="108" cy="30" r="3" className={WARM} />
    </>
  ),
};

/** Decorative: the words beside it say everything the picture does. */
export function Illustration({ name, className }: { name: IllustrationName; className?: string }) {
  return (
    <svg viewBox="0 0 160 120" aria-hidden className={cn("h-28 w-auto", className)}>
      {drawings[name]}
    </svg>
  );
}
