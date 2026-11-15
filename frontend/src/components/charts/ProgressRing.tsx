import { cn } from "@/lib/utils";

/** A ring that fills as steps complete. The count in the middle says the same thing in words. */
export function ProgressRing({ done, total, size = 64, className }: { done: number; total: number; size?: number; className?: string }) {
  const stroke = 6;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - (total === 0 ? 0 : done / total));
  return (
    <span role="img" aria-label={`${done} of ${total} steps done`} className={cn("relative inline-grid shrink-0 place-items-center", className)} style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" strokeWidth={stroke} className="stroke-surface-muted" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="stroke-primary transition-[stroke-dashoffset] duration-700 ease-out motion-reduce:transition-none"
        />
      </svg>
      <span aria-hidden className="absolute text-sm font-semibold">
        {done}/{total}
      </span>
    </span>
  );
}
