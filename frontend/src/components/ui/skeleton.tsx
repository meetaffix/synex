import { cn } from "@/lib/utils";

function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("relative overflow-hidden rounded-sm bg-surface-muted before:absolute before:inset-0 before:animate-[shimmer_1.8s_ease-in-out_infinite] before:bg-gradient-to-r before:from-transparent before:via-surface/70 before:to-transparent motion-reduce:before:hidden", className)}
      {...props}
    />
  );
}

export { Skeleton };
