import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  // 150ms ease-out press and hover; reduced motion drops the press scale.
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-[background-color,color,border-color,transform] duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50 active:scale-[0.98] motion-reduce:active:scale-100 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        /** The one primary action on a view: a filled teal pill. */
        default: "rounded-full bg-primary font-semibold text-primary-foreground hover:bg-primary-hover",
        /** Quieter actions. "outline" is the same look, kept for existing callers. */
        secondary: "border border-border-strong bg-surface text-foreground hover:bg-surface-muted",
        outline: "border border-border-strong bg-surface text-foreground hover:bg-surface-muted",
        ghost: "text-foreground hover:bg-surface-muted",
        /** Destructive actions are never primary: danger text on a soft tint. */
        danger: "border border-danger/40 bg-danger-soft text-danger hover:border-danger",
        destructive: "border border-danger/40 bg-danger-soft text-danger hover:border-danger",
        link: "h-auto px-0 text-primary underline underline-offset-4 hover:text-primary-hover",
      },
      size: {
        // 40px; 36px compact for dense tables; at least 44px on phones.
        default: "h-10 px-5 max-sm:h-11",
        sm: "h-9 px-3 max-sm:h-11",
        lg: "h-11 px-6 text-base",
        icon: "size-10 max-sm:size-11",
        "icon-sm": "size-9 max-sm:size-11",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  loading?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    { className, variant, size, asChild = false, loading, children, disabled, ...props },
    ref
  ) => {
    const Comp = asChild ? Slot : "button";
    if (asChild) {
      return (
        <Comp
          className={cn(buttonVariants({ variant, size, className }))}
          ref={ref}
          {...props}
        >
          {children}
        </Comp>
      );
    }
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        disabled={disabled || loading}
        {...props}
      >
        {loading && <Loader2 className="animate-spin" />}
        {children}
      </Comp>
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
