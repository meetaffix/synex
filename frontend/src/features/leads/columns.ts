import { useCallback, useState } from "react";

/** Columns a person can add to the Contacts table. Name, Company, Email and Status are always shown. */
export const OPTIONAL_COLUMNS = [
  { key: "title", label: "Title" },
  { key: "location", label: "Location" },
  { key: "phone", label: "Phone" },
  { key: "industry", label: "Industry" },
] as const;

export type OptionalColumn = (typeof OPTIONAL_COLUMNS)[number]["key"];

const DEFAULT: OptionalColumn[] = [];
const storageKey = (userId: string | undefined) => `synex.leads.columns.${userId ?? "signed-out"}`;
const known = new Set<string>(OPTIONAL_COLUMNS.map((column) => column.key));

function read(userId: string | undefined): OptionalColumn[] {
  try {
    const raw = localStorage.getItem(storageKey(userId));
    if (!raw) return DEFAULT;
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((key): key is OptionalColumn => typeof key === "string" && known.has(key)) : DEFAULT;
  } catch {
    return DEFAULT;
  }
}

/** The optional columns this person chose, remembered in this browser for them. */
export function useLeadColumns(userId: string | undefined) {
  const [chosen, setChosen] = useState<OptionalColumn[]>(() => read(userId));
  const [owner, setOwner] = useState(userId);
  if (owner !== userId) {
    setOwner(userId);
    setChosen(read(userId));
  }

  const toggle = useCallback(
    (key: OptionalColumn) =>
      setChosen((current) => {
        const next = current.includes(key) ? current.filter((k) => k !== key) : [...current, key];
        const ordered = OPTIONAL_COLUMNS.map((column) => column.key).filter((k) => next.includes(k));
        try {
          localStorage.setItem(storageKey(userId), JSON.stringify(ordered));
        } catch {
          /* a convenience only */
        }
        return ordered;
      }),
    [userId],
  );

  return { chosen, toggle, shows: (key: OptionalColumn) => chosen.includes(key) };
}
