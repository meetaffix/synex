import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/services/client";
export interface Account {
  id: string;
  name: string;
  picture: string | null;
  email: string | null;
  status: string;
  scopes: string[];
  checkedAt: string | null;
  expiresAt: string | null;
  capabilities: Record<string, string>;
}
export interface Post {
  hasImage: boolean;
  id: string;
  title: string;
  body: string;
  accountId: string | null;
  status: string;
  scheduledAt: string | null;
  timezone: string;
  version: number;
  attempts: number;
  error: string | null;
  linkedinId: string | null;
  createdAt: string;
  updatedAt: string;
}
export interface Activity {
  id: string;
  postId: string;
  status: string;
  detail: string;
  createdAt: string;
}
export function usePosts() {
  return useQuery({
    queryKey: ["publishing", "posts"],
    queryFn: () => api.get<Post[]>("/publishing/posts"),
    refetchInterval: 15000,
  });
}
export function useAccounts() {
  return useQuery({
    queryKey: ["publishing", "accounts"],
    queryFn: () => api.get<Account[]>("/linkedin/accounts"),
  });
}
export function useActivity() {
  return useQuery({
    queryKey: ["publishing", "activity"],
    queryFn: () => api.get<Activity[]>("/publishing/activity"),
    refetchInterval: 15000,
  });
}
export function usePreferences() {
  return useQuery({
    queryKey: ["publishing", "preferences"],
    queryFn: () => api.get<{ timezone: string }>("/publishing/preferences"),
  });
}
export function useRefresh() {
  const q = useQueryClient();
  return () => q.invalidateQueries({ queryKey: ["publishing"] });
}
export const statusLabel = (s: string) =>
  ({
    reconnect_required: "Reconnect required",
    needs_review: "Needs review",
    retrying: "Retry scheduled",
  })[s] ?? s.charAt(0).toUpperCase() + s.slice(1).replaceAll("_", " ");
export function formatDate(value: string | null, zone?: string) {
  return value
    ? new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: zone,
      }).format(new Date(value))
    : "—";
}
export function dayKey(date: Date, zone: string) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}
// Convert an explicit wall time in an IANA zone; reject non-existent DST times.
export function zonedInstant(value: string, zone: string) {
  const wall = new Date(value + "Z").getTime();
  if (!Number.isFinite(wall)) throw new Error("Choose a valid date and time.");
  let guess = wall;
  const local = (ms: number) => {
    const p = new Intl.DateTimeFormat("en-CA", {
      timeZone: zone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).formatToParts(new Date(ms));
    const get = (t: string) => p.find((x) => x.type === t)!.value;
    return `${get("year")}-${get("month")}-${get("day")}T${get("hour")}:${get("minute")}`;
  };
  for (let i = 0; i < 4; i++)
    guess += wall - new Date(local(guess) + "Z").getTime();
  if (local(guess) !== value)
    throw new Error(
      "This local time does not exist because the clocks change. Choose another time.",
    );
  return new Date(guess).toISOString();
}
