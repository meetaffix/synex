import type { LucideIcon } from "lucide-react";
import { Illustration, type IllustrationName } from "@/components/brand/Illustration";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  /** Either a drawn illustration (the brand set) or a plain icon in a primary-soft circle. */
  illustration?: IllustrationName;
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({
  icon: Icon,
  illustration,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-lg border border-border bg-surface px-4 py-12 text-center sm:px-6",
        className
      )}
    >
      {illustration ? (
        <Illustration name={illustration} className="mb-4 h-28" />
      ) : (
        Icon && (
          <div aria-hidden className="mb-4 grid size-12 place-items-center rounded-full bg-primary-soft text-primary-soft-foreground">
            <Icon className="size-6" />
          </div>
        )
      )}
      <h2 className="text-base font-semibold">{title}</h2>
      {description && (
        <p className="mt-2 max-w-md text-sm text-muted-foreground">
          {description}
        </p>
      )}
      {action && <div className="mt-6 flex flex-wrap justify-center gap-3">{action}</div>}
    </div>
  );
}
