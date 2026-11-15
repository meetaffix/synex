import * as React from "react";
import { cn } from "@/lib/utils";

/** A native radio drawn to the design system: keyboard, grouping and form behaviour come from the browser. */
const Radio = React.forwardRef<HTMLInputElement, Omit<React.InputHTMLAttributes<HTMLInputElement>, "type">>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      type="radio"
      className={cn(
        "size-5 shrink-0 cursor-pointer appearance-none rounded-full border border-input bg-surface transition-[border-color,box-shadow] duration-150",
        "checked:border-primary checked:shadow-[inset_0_0_0_4px_rgb(var(--surface)),inset_0_0_0_10px_rgb(var(--primary))]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  ),
);
Radio.displayName = "Radio";

export { Radio };
