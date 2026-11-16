import * as React from "react";
import { cn } from "@/lib/utils";

export interface TabItem {
  id: string;
  label: string;
}

interface TabsProps {
  label: string;
  tabs: TabItem[];
  value: string;
  onChange: (id: string) => void;
  idPrefix?: string;
  className?: string;
}

/** A row of tabs with the keyboard pattern screen readers expect: arrows move, Home and End jump, the active tab is the one tab stop. */
export function Tabs({ label, tabs, value, onChange, idPrefix = "tab", className }: TabsProps) {
  const refs = React.useRef<Record<string, HTMLButtonElement | null>>({});
  const move = (to: number) => {
    const next = tabs[(to + tabs.length) % tabs.length];
    onChange(next.id);
    refs.current[next.id]?.focus();
  };
  return (
    <div
      role="tablist"
      aria-label={label}
      className={cn("flex gap-1 overflow-x-auto border-b border-border", className)}
      onKeyDown={(event) => {
        const index = tabs.findIndex((tab) => tab.id === value);
        if (event.key === "ArrowRight") move(index + 1);
        else if (event.key === "ArrowLeft") move(index - 1);
        else if (event.key === "Home") move(0);
        else if (event.key === "End") move(tabs.length - 1);
        else return;
        event.preventDefault();
      }}
    >
      {tabs.map((tab) => {
        const active = tab.id === value;
        return (
          <button
            key={tab.id}
            ref={(node) => {
              refs.current[tab.id] = node;
            }}
            type="button"
            role="tab"
            id={`${idPrefix}-${tab.id}`}
            aria-selected={active}
            aria-controls={`${idPrefix}-panel-${tab.id}`}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(tab.id)}
            className={cn(
              "-mb-px shrink-0 whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors duration-150",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
              active ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

export function TabPanel({ id, active, idPrefix = "tab", children }: { id: string; active: boolean; idPrefix?: string; children: React.ReactNode }) {
  return (
    <div role="tabpanel" id={`${idPrefix}-panel-${id}`} aria-labelledby={`${idPrefix}-${id}`} hidden={!active} tabIndex={0} className="pt-6 focus-visible:outline-none">
      {active ? children : null}
    </div>
  );
}
