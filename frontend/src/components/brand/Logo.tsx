import { cn } from "@/lib/utils";

/** The Synex mark, as the owner supplied it: one solid orange shape, the same in both themes. */
export const MARK_PATH = "M196 236H325A84 84 0 0 1 408 320V405A103 103 0 0 0 510 508H567A103 103 0 0 0 670 405V320A84 84 0 0 1 755 236H884A36 36 0 0 1 920 272V380C920 428 886 469 840 483L770 503C716 520 680 566 680 620V768A108 108 0 0 1 572 876H510A108 108 0 0 1 402 768V620C402 566 366 520 312 503L240 483C194 469 160 428 160 380V272A36 36 0 0 1 196 236Z";

export function LogoMark({ size = 32, className }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="140 156 800 800" role="img" aria-label="Synex" className={cn("shrink-0", className)}>
      <path d={MARK_PATH} fill="rgb(var(--logo))" />
    </svg>
  );
}

/** Mark and wordmark together. The wordmark is set in the app's own font. */
export function Logo({ size = 32, showWordmark = true, className }: { size?: number; showWordmark?: boolean; className?: string }) {
  if (!showWordmark) return <LogoMark size={size} className={className} />;
  return (
    <span className={cn("inline-flex items-center gap-2", className)} role="img" aria-label="Synex">
      <LogoMark size={size} className="[&]:pointer-events-none" />
      <span aria-hidden className="font-semibold tracking-tight text-foreground" style={{ fontSize: size * 0.66 }}>Synex</span>
    </span>
  );
}
