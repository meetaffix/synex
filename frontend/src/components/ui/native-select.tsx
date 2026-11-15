import * as React from "react";
import { cn } from "@/lib/utils";

/** A styled native select: keyboard and screen-reader behaviour comes from the browser. */
const NativeSelect = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, ...props }, ref) => (
    <select
      ref={ref}
      className={cn(
"h-10 max-sm:h-11",
        "flex w-full rounded-sm border border-input bg-surface px-3 text-sm text-foreground transition-colors duration-150",
        "placeholder:text-subtle",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        "aria-[invalid=true]:border-danger",
        "disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-muted-foreground",
        className,
      )}
      {...props}
    />
  ),
);
NativeSelect.displayName = "NativeSelect";

export { NativeSelect };
