import { formatDistanceToNow, format, isToday, isYesterday } from "date-fns";

export function formatNumber(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

export function formatPercent(value: number, fractionDigits = 1): string {
  return `${value.toFixed(fractionDigits)}%`;
}

/** "3 hours ago" */
export function formatRelative(date: string | Date): string {
  const d = typeof date === "string" ? new Date(date) : date;
  return formatDistanceToNow(d, { addSuffix: true });
}

/** Smart timestamp for inbox / activity rows. */
export function formatSmartTime(date: string | Date): string {
  const d = typeof date === "string" ? new Date(date) : date;
  if (isToday(d)) return format(d, "h:mm a");
  if (isYesterday(d)) return "Yesterday";
  return format(d, "MMM d");
}

export function formatDate(date: string | Date, pattern = "MMM d, yyyy"): string {
  const d = typeof date === "string" ? new Date(date) : date;
  return format(d, pattern);
}

/** "John Doe" -> "JD" */
export function getInitials(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}
