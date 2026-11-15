import { useEffect, useRef, type ReactNode } from "react";

/** Each step takes focus on mount so keyboard and screen-reader users land on the new content. */
export function StepHeading({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    ref.current?.focus();
  }, []);
  return (
    <h3 ref={ref} tabIndex={-1} className="text-base font-semibold outline-none">
      {children}
    </h3>
  );
}
