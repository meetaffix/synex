import { useMemo, useState } from "react";

export type SortDirection = "asc" | "desc";
export type SortValue = string | number | null | undefined;

/** Client-side sorting for a table whose rows are already loaded. Empty values always sort last. */
export function useSort<T, K extends string>(rows: T[], columns: Record<K, (row: T) => SortValue>, initial: { key: NoInfer<K>; direction: SortDirection }) {
  const [sort, setSort] = useState<{ key: K; direction: SortDirection }>(initial);

  const sorted = useMemo(() => {
    const value = columns[sort.key];
    const factor = sort.direction === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const x = value(a);
      const y = value(b);
      if (x == null || x === "") return y == null || y === "" ? 0 : 1;
      if (y == null || y === "") return -1;
      if (typeof x === "number" && typeof y === "number") return (x - y) * factor;
      return String(x).localeCompare(String(y), undefined, { sensitivity: "base", numeric: true }) * factor;
    });
    // `columns` is a static map at every call site.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, sort]);

  const toggle = (key: K) =>
    setSort((current) => ({ key, direction: current.key === key && current.direction === "asc" ? "desc" : "asc" }));

  return { sorted, sort, toggle };
}
