import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { api, ApiError } from "@/services/client";

export const INTEREST_LABEL: Record<string, string> = { interested: "Interested", not_interested: "Not interested", meeting_booked: "Meeting booked", wrong_person: "Wrong person", follow_up_later: "Follow up later" };

const itemSchema = z.object({
  id: z.string(),
  leadId: z.string(),
  leadName: z.string(),
  leadTitle: z.string().nullable().optional(),
  leadCompany: z.string().nullable().optional(),
  linkedinUrl: z.string().nullable().optional(),
  accountId: z.string().nullable(),
  accountName: z.string().nullable().optional(),
  campaignId: z.string().nullable(),
  campaignName: z.string().nullable().optional(),
  lastMessagePreview: z.string().nullable().optional(),
  lastMessageAt: z.string().nullable(),
  unread: z.boolean(),
  status: z.string(),
  starred: z.boolean(),
  answered: z.boolean(),
  tags: z.array(z.string()),
  interest: z.string().nullable(),
  hasDraft: z.boolean(),
  draftBody: z.string().default(""),
  scheduledCount: z.number(),
  lastDirection: z.string().nullable(),
  needsReply: z.boolean(),
});
export type InboxItem = z.infer<typeof itemSchema>;
const listSchema = z.object({ items: z.array(itemSchema), total: z.number() });
const metaSchema = z.object({
  accounts: z.array(z.object({ id: z.string(), name: z.string(), lastSyncedAt: z.string().nullable(), live: z.boolean() })),
  campaigns: z.array(z.object({ id: z.string(), name: z.string() })),
  tags: z.array(z.string()),
  interests: z.array(z.object({ id: z.string(), label: z.string() })),
});
const messageSchema = z.object({ id: z.string(), direction: z.enum(["inbound", "outbound"]), body: z.string(), sentAt: z.string(), deliveryStatus: z.string().optional(), deliveryError: z.string().nullable().optional() });
export type Message = z.infer<typeof messageSchema>;
const scheduledSchema = z.array(z.object({ id: z.string(), body: z.string(), sendAt: z.string(), status: z.string(), error: z.string().nullable() }));

export interface InboxFilter {
  q: string;
  needsReply: boolean;
  iMessagedLast: boolean;
  unread: boolean;
  starred: boolean;
  drafts: boolean;
  scheduled: boolean;
  archived: boolean;
  tag: string;
  interest: string;
  accounts: string[];
  campaigns: string[];
  campaignMode: "include" | "exclude";
  where: "" | "messages_sent" | "responses";
  preset: string;
  dateFrom: string;
  dateTo: string;
}
export const emptyFilter = (): InboxFilter => ({ q: "", needsReply: false, iMessagedLast: false, unread: false, starred: false, drafts: false, scheduled: false, archived: false, tag: "", interest: "", accounts: [], campaigns: [], campaignMode: "include", where: "", preset: "", dateFrom: "", dateTo: "" });

export const PRESETS: [string, string][] = [["", "Any time"], ["today", "Today"], ["yesterday", "Yesterday"], ["week", "Last week"], ["month", "Last month"], ["quarter", "Last quarter"], ["custom", "Custom range"]];

/** The start and end a preset means, in the person's own time zone. */
export function presetRange(preset: string, from: string, to: string, now = new Date()): { from?: string; to?: string } {
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const daysAgo = (n: number) => new Date(startOfDay(now).getTime() - n * 86_400_000);
  if (preset === "today") return { from: startOfDay(now).toISOString() };
  if (preset === "yesterday") return { from: daysAgo(1).toISOString(), to: startOfDay(now).toISOString() };
  if (preset === "week") return { from: daysAgo(7).toISOString() };
  if (preset === "month") return { from: daysAgo(30).toISOString() };
  if (preset === "quarter") return { from: daysAgo(90).toISOString() };
  if (preset === "custom") return { from: from ? new Date(`${from}T00:00:00`).toISOString() : undefined, to: to ? new Date(`${to}T23:59:59`).toISOString() : undefined };
  return {};
}

export function toParams(f: InboxFilter): URLSearchParams {
  const p = new URLSearchParams();
  const flag = (key: string, on: boolean) => on && p.set(key, "true");
  if (f.q.trim()) p.set("q", f.q.trim());
  flag("needs_reply", f.needsReply); flag("i_messaged_last", f.iMessagedLast); flag("unread", f.unread); flag("starred", f.starred);
  flag("drafts", f.drafts); flag("scheduled", f.scheduled); flag("archived", f.archived);
  if (f.tag) p.set("tag", f.tag);
  if (f.interest) p.set("interest", f.interest);
  if (f.accounts.length) p.set("accounts", f.accounts.join(","));
  if (f.campaigns.length) { p.set("campaigns", f.campaigns.join(",")); p.set("campaign_mode", f.campaignMode); }
  if (f.where) p.set("where", f.where);
  const range = presetRange(f.preset, f.dateFrom, f.dateTo);
  if (range.from) p.set("date_from", range.from);
  if (range.to) p.set("date_to", range.to);
  return p;
}

function read<S extends z.ZodType>(schema: S, data: unknown): z.infer<S> {
  const result = schema.safeParse(data);
  if (!result.success) throw new ApiError(0, "The server sent a response Synex could not read. Try again.");
  return result.data;
}

export const useInboxList = (f: InboxFilter) =>
  useQuery({ queryKey: ["inbox", "list", toParams(f).toString()], queryFn: async () => read(listSchema, await api.get(`/inbox/conversations?${toParams(f)}`)), refetchInterval: 30_000, placeholderData: (previous) => previous });
export const useInboxMeta = () => useQuery({ queryKey: ["inbox", "meta"], queryFn: async () => read(metaSchema, await api.get("/inbox/meta")), staleTime: 60_000 });
export const useThread = (id: string | null) =>
  useQuery({ queryKey: ["inbox", "thread", id], enabled: !!id, queryFn: async () => read(z.array(messageSchema), await api.get(`/conversations?conversationId=${encodeURIComponent(id!)}`)) });
export const useScheduled = (id: string | null) => useQuery({ queryKey: ["inbox", "scheduled", id], enabled: !!id, queryFn: async () => read(scheduledSchema, await api.get(`/inbox/${id}/scheduled`)) });
export const useSuggestCost = () => useQuery({ queryKey: ["inbox", "suggest-cost"], queryFn: async () => read(z.object({ provider: z.string(), estimatedUsd: z.number() }), await api.get("/inbox/suggest-cost")), staleTime: 300_000 });

export type BulkAction = "read" | "unread" | "star" | "unstar" | "archive" | "unarchive" | "answered" | "unanswered" | "tag_add" | "tag_remove" | "interest";

export function useInboxActions() {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: ["inbox"] });
  return {
    bulk: useMutation({ mutationFn: (v: { ids: string[]; action: BulkAction; value?: string }) => api.post("/inbox/bulk", v), onSuccess: refresh }),
    refreshSenders: useMutation({ mutationFn: (accountIds: string[]) => api.post<{ queued: number; skipped: { account: string; reason: string }[] }>("/inbox/refresh", { accountIds }), onSuccess: () => window.setTimeout(refresh, 4000) }),
    saveDraft: useMutation({ mutationFn: (v: { id: string; body: string }) => api.put(`/inbox/${v.id}/draft`, { body: v.body }) }),
    schedule: useMutation({ mutationFn: (v: { id: string; body: string; sendAt: string }) => api.post(`/inbox/${v.id}/schedule`, { body: v.body, sendAt: v.sendAt }), onSuccess: refresh }),
    cancelScheduled: useMutation({ mutationFn: (id: string) => api.delete(`/inbox/scheduled/${id}`), onSuccess: refresh }),
    suggest: useMutation({ mutationFn: (id: string) => api.post<{ text: string; source: string; provider: string }>(`/inbox/${id}/suggest-reply`) }),
    reply: useMutation({ mutationFn: (v: { id: string; body: string }) => api.post("/conversations", { action: "reply", conversationId: v.id, body: v.body }), onSuccess: refresh }),
  };
}

export const exportUrlParams = (f: InboxFilter) => toParams(f).toString();
export const exportCsv = (f: InboxFilter) => api.getText(`/inbox/export?${toParams(f)}`);
