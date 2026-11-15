import * as React from "react";
import { cn } from "@/lib/utils";

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
"h-10 py-2 max-sm:h-11 file:mr-3 file:rounded-sm file:border-0 file:bg-surface-muted file:px-3 file:py-1 file:text-sm file:font-medium file:text-foreground",
          "flex w-full rounded-sm border border-input bg-surface px-3 text-sm text-foreground transition-colors duration-150",
          "placeholder:text-subtle",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
          "aria-[invalid=true]:border-danger",
          "disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-muted-foreground",
          "file:border-0 file:bg-transparent file:text-sm file:font-medium",
          className
        )}
        ref={ref}
        {...props}
      />
    );
  }
);
Input.displayName = "Input";

export { Input };
