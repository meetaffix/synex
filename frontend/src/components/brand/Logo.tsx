import { useId } from "react";
import { cn } from "@/lib/utils";

/** The Synex mark: two profiles joined by a rising path, on the brand gradient. Draws the same in both themes. */
export function LogoMark({ size = 32, className }: { size?: number; className?: string }) {
  const gradient = useId();
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" role="img" aria-label="Synex" className={cn("shrink-0", className)}>
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" style={{ stopColor: "rgb(var(--brand-from))" }} />
          <stop offset="1" style={{ stopColor: "rgb(var(--brand-to))" }} />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill={`url(#${gradient})`} />
      {/* the rising path */}
      <path d="M9.5 22.5c0-6.5 13-3.5 13-11" fill="none" stroke="rgb(var(--brand-text))" strokeWidth="2.6" strokeLinecap="round" />
      {/* the two profiles it joins */}
      <circle cx="9.5" cy="22.5" r="3" fill="rgb(var(--brand-text))" />
      <circle cx="22.5" cy="11.5" r="3" fill="rgb(var(--brand-accent))" />
    </svg>
  );
}

/** Mark and wordmark as one SVG. The wordmark is set in the app's own font (Plus Jakarta Sans, bundled). */
export function Logo({ size = 32, showWordmark = true, className }: { size?: number; showWordmark?: boolean; className?: string }) {
  if (!showWordmark) return <LogoMark size={size} className={className} />;
  const width = size * 3.6;
  return (
    <span className={cn("inline-flex items-center", className)}>
      <svg width={width} height={size} viewBox="0 0 115 32" role="img" aria-label="Synex" className="overflow-visible">
        <LogoMarkInner />
        <text x="41" y="22.5" fontFamily='"Plus Jakarta Sans", ui-sans-serif, system-ui, sans-serif' fontSize="22" fontWeight="700" letterSpacing="-0.4" fill="currentColor">
          Synex
        </text>
      </svg>
    </span>
  );
}

function LogoMarkInner() {
  const gradient = useId();
  return (
    <>
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" style={{ stopColor: "rgb(var(--brand-from))" }} />
          <stop offset="1" style={{ stopColor: "rgb(var(--brand-to))" }} />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill={`url(#${gradient})`} />
      <path d="M9.5 22.5c0-6.5 13-3.5 13-11" fill="none" stroke="rgb(var(--brand-text))" strokeWidth="2.6" strokeLinecap="round" />
      <circle cx="9.5" cy="22.5" r="3" fill="rgb(var(--brand-text))" />
      <circle cx="22.5" cy="11.5" r="3" fill="rgb(var(--brand-accent))" />
    </>
  );
}
