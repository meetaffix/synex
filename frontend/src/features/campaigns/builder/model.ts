import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { api, ApiError } from "@/services/client";

/** The campaign as the builder edits it. Everything optional on the server is given a value here so the form never holds undefined. */

export const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;
export type Day = (typeof DAYS)[number];
export const DAY_LABEL: Record<Day, string> = { mon: "Monday", tue: "Tuesday", wed: "Wednesday", thu: "Thursday", fri: "Friday", sat: "Saturday", sun: "Sunday" };
export type WeekSchedule = Record<Day, { on: boolean; start: string; end: string }>;
export const defaultWeek = (): WeekSchedule => Object.fromEntries(DAYS.map((d) => [d, { on: d !== "sat" && d !== "sun", start: "08:00", end: "20:00" }])) as WeekSchedule;

export const EXCLUSIONS = [
  { key: "other_campaigns", label: "Exclude leads present in other campaigns" },
  { key: "reached_other_campaigns", label: "Exclude leads already reached through other campaigns" },
  { key: "reached_same_sender", label: "Exclude leads already reached by the same sender through other campaigns" },
  { key: "messaged_other_senders", label: "Exclude leads messaged by other senders" },
  { key: "existing_connections", label: "Exclude existing LinkedIn connections" },
] as const;
export type ExclusionKey = (typeof EXCLUSIONS)[number]["key"];

export const TONES = [["auto", "Auto"], ["professional", "Professional"], ["casual", "Casual"], ["witty", "Witty"], ["direct", "Direct"]] as const;
export const STRATEGIES = [["auto", "Auto"], ["common_ground", "Common ground"], ["value_offer", "Value offer"], ["curiosity_hook", "Curiosity hook"]] as const;

const aiConfigSchema = z.object({
  mode: z.enum(["direct", "ai"]),
  tone: z.string(),
  strategy: z.string(),
  instructions: z.string(),
  profile_data: z.record(z.string(), z.boolean()),
});
export type AiConfig = z.infer<typeof aiConfigSchema>;
export const defaultAi = (): AiConfig => ({ mode: "direct", tone: "auto", strategy: "auto", instructions: "", profile_data: { role_company: true, recent_posts: false, skills: false, career: false, interests: false } });

export type StepType = "connection_request" | "wait" | "message" | "follow_up" | "end";
export interface BuilderStep {
  key: number;
  id?: string;
  type: StepType;
  message: string;
  delayHours: number;
  aiConfig: AiConfig | null;
}

const stepSchema = z.object({
  id: z.string(),
  type: z.string(),
  order: z.number(),
  message: z.string().nullable(),
  delayHours: z.number().nullable(),
  aiConfig: aiConfigSchema.nullable().optional(),
});

const campaignSchema = z.object({
  id: z.string(),
  name: z.string(),
  status: z.string(),
  accountId: z.string().nullable(),
  accountIds: z.array(z.string()),
  leadListId: z.string().nullable(),
  leadListName: z.string(),
  dailyConnectionLimit: z.number().nullable(),
  dailyMessageLimit: z.number().nullable(),
  schedule: z.object({ timezone: z.string().nullable() }).passthrough(),
  weekSchedule: z.record(z.string(), z.object({ on: z.boolean(), start: z.string(), end: z.string() })).nullable().optional(),
  exclusions: z.record(z.string(), z.boolean()),
  allocation: z.record(z.string(), z.record(z.string(), z.number())),
  aiContext: z.record(z.string(), z.unknown()),
  launchSummary: z.object({ enrolled: z.number(), excluded: z.record(z.string(), z.number()) }).nullable().optional(),
  steps: z.array(stepSchema),
});
export type ServerCampaign = z.infer<typeof campaignSchema>;

export interface BuilderState {
  name: string;
  accountIds: string[];
  leadListId: string | null;
  timezone: string;
  week: WeekSchedule;
  exclusions: Record<string, boolean>;
  allocation: Record<string, Record<string, number>>;
  context: Record<string, unknown>;
  steps: BuilderStep[];
}

let key = 1;
export const newStep = (type: StepType): BuilderStep => ({ key: key++, type, message: "", delayHours: type === "wait" ? 24 : 0, aiConfig: null });

export const fromServer = (c: ServerCampaign): BuilderState => ({
  name: c.name,
  accountIds: [...new Set([c.accountId, ...c.accountIds].filter((x): x is string => !!x))],
  leadListId: c.leadListId,
  timezone: c.schedule.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone ?? "UTC",
  week: { ...defaultWeek(), ...(c.weekSchedule ?? {}) } as WeekSchedule,
  exclusions: c.exclusions,
  allocation: c.allocation,
  context: c.aiContext,
  steps: c.steps.map((s) => ({ key: key++, id: s.id, type: s.type as StepType, message: s.message ?? "", delayHours: s.delayHours ?? 0, aiConfig: s.aiConfig ?? null })),
});

const WRITES: StepType[] = ["connection_request", "message", "follow_up"];

/** The body the server takes on save. Step ids are kept so drafts and runs stay attached to their step. */
export const toPayload = (s: BuilderState) => ({
  name: s.name.trim() || "Untitled campaign",
  accountId: s.accountIds[0] ?? null,
  accountIds: s.accountIds.slice(1),
  leadListId: s.leadListId,
  timezone: s.timezone,
  weekSchedule: s.week,
  exclusions: s.exclusions,
  allocation: s.allocation,
  aiContext: s.context,
  steps: s.steps.map((st, order) => ({
    id: st.id,
    type: st.type,
    order,
    message: WRITES.includes(st.type) ? st.message : null,
    delayHours: st.type === "wait" ? st.delayHours : null,
    aiConfig: st.aiConfig,
  })),
});

function read<S extends z.ZodType>(schema: S, data: unknown): z.infer<S> {
  const result = schema.safeParse(data);
  if (!result.success) throw new ApiError(0, "The server sent a response Synex could not read. Try again.");
  return result.data;
}

export const campaignKey = (id: string) => ["campaign", id] as const;

export const useBuilderCampaign = (id: string) =>
  useQuery({ queryKey: campaignKey(id), queryFn: async () => read(campaignSchema, await api.get(`/campaigns?id=${id}`)), staleTime: Infinity, refetchOnWindowFocus: false });

export const useSaveCampaign = (id: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (state: BuilderState) => read(campaignSchema, await api.post("/campaigns", { action: "update", id, ...toPayload(state) })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["campaigns"] }),
  });
};

const problemSchema = z.object({ kind: z.string(), field: z.string(), message: z.string(), step: z.string() });
const checkSchema = z.object({ ready: z.boolean(), problems: z.array(problemSchema) });
export type LaunchProblem = z.infer<typeof problemSchema>;
export const useLaunchCheck = (id: string, version: number) =>
  useQuery({ queryKey: ["launch-check", id, version], queryFn: async () => read(checkSchema, await api.get(`/campaigns/${id}/launch-check`)), staleTime: 0 });

const estimateSchema = z.object({ count: z.number(), available: z.number(), existing: z.number(), cap: z.number(), capped: z.boolean(), provider: z.string(), estimatedSeconds: z.number(), estimatedUsd: z.number(), note: z.string() });
const draftSchema = z.object({ id: z.string(), leadId: z.string(), leadName: z.string(), stepId: z.string(), stepOrder: z.number().nullable(), stepType: z.string().nullable(), body: z.string(), status: z.string(), source: z.string() });
const draftListSchema = z.object({ counts: z.record(z.string(), z.number()), drafts: z.array(draftSchema), job: z.object({ state: z.string(), requested: z.number(), created: z.number(), error: z.string().nullable() }).passthrough().nullable() });
export type Draft = z.infer<typeof draftSchema>;
const previewSchema = z.object({ text: z.string(), source: z.string(), provider: z.string(), leadName: z.string(), estimatedUsd: z.number() });

export const draftsApi = {
  estimate: async (id: string) => read(estimateSchema, await api.post(`/campaigns/${id}/drafts/estimate`)),
  list: async (id: string) => read(draftListSchema, await api.get(`/campaigns/${id}/drafts`)),
  generate: async (id: string, confirmedCount: number) => api.post(`/campaigns/${id}/drafts/generate`, { confirmedCount }),
  approve: async (id: string, all: boolean, draftIds?: string[]) => api.post(`/campaigns/${id}/drafts/approve`, { all, draftIds }),
  edit: async (id: string, draftId: string, body: string) => api.patch(`/campaigns/${id}/drafts/${draftId}`, { body }),
  preview: async (id: string, stepType: string, config: AiConfig | null, leadId?: string) => read(previewSchema, await api.post(`/campaigns/${id}/drafts/preview`, { stepType, config, leadId })),
};
export const useDrafts = (id: string, poll: boolean) =>
  useQuery({ queryKey: ["drafts", id], queryFn: () => draftsApi.list(id), refetchInterval: (q) => (poll || q.state.data?.job?.state === "running" ? 2000 : false) });
