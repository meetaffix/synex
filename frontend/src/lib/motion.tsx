import { useEffect, useRef, useState, type CSSProperties, type ElementType, type ReactNode } from "react";
import { cn } from "@/lib/utils";

/** True when the person asked their device for less motion. Motion in this app is decoration; it never carries meaning. */
export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Counts up to `value` the first time it appears (about 700ms, ease-out), then follows later changes at once. */
export function useCountUp(value: number | null | undefined, duration = 700): number | null {
  const [shown, setShown] = useState<number | null>(() => (value == null || prefersReducedMotion() ? (value ?? null) : 0));
  const played = useRef(false);

  useEffect(() => {
    if (value == null) {
      setShown(null);
      return;
    }
    if (played.current || prefersReducedMotion()) {
      setShown(value);
      played.current = true;
      return;
    }
    played.current = true;
    let frame = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / duration);
      setShown(Math.round(value * (1 - Math.pow(1 - progress, 3))));
      if (progress < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value, duration]);

  return shown;
}

/** Fades and rises into place (200ms). With `index`, items in a list arrive one after another. */
export function Reveal({ children, index = 0, as: Tag = "div", className, style }: { children: ReactNode; index?: number; as?: ElementType; className?: string; style?: CSSProperties }) {
  return (
    <Tag className={cn("animate-rise", className)} style={{ animationDelay: `${Math.min(index, 10) * 45}ms`, ...style }}>
      {children}
    </Tag>
  );
}
