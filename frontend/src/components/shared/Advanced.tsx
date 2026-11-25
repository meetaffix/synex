import type { ReactNode } from "react";

/** Technical and operator settings a normal user does not need day to day. Kept, but folded away. */
export function Advanced({ label, children }: { label: string; children: ReactNode }) {
  return (
    <details className="group grid gap-4 rounded-lg border border-border p-4 [&[open]>summary]:mb-4">
      <summary className="cursor-pointer select-none rounded-md py-1 text-sm font-medium text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{label}</summary>
      {children}
    </details>
  );
}
