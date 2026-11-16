import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { api, ApiError } from "@/services/client";

/** Everything behind an account's own page: its per-action budgets, privacy, health and lifecycle. */
const actionPolicySchema = z.object({
  dailyLimit: z.number(),
  increaseBy: z.number(),
  stopAt: z.number(),
  intervalDays: z.number(),
  dynamicInterval: z.boolean(),
});

export const presetSchema = z.enum(["off", "conservative", "balanced", "aggressive", "custom"]);

export const policySchema = z.object({
  preset: presetSchema,
  range: z.number(),
  actions: z.record(actionPolicySchema),
  autoWithdraw: z.boolean(),
  staleInviteDays: z.number(),
  inboxHistoryDays: z.number(),
});

const usageRowSchema = z.object({
  action: z.string(),
  label: z.string(),
  used: z.number(),
  low: z.number(),
  high: z.number(),
  budget: z.number(),
  ceiling: z.number(),
});

export const detailsSchema = z.object({
  accountId: z.string(),
  lifecycle: z.string(),
  activeCampaigns: z.number(),
  canChangePrivacy: z.boolean(),
  policy: policySchema,
  usage: z.array(usageRowSchema),
  ssi: z.number().nullable(),
  ssiReason: z.string(),
  activity: z.array(z.object({ id: z.string(), step: z.string(), status: z.string(), message: z.string().nullable(), createdAt: z.string() })),
});

export const overviewSchema = z.object({
  plan: z.string(),
  planPlaceholder: z.boolean(),
  seatsUsed: z.number(),
  seatsIncluded: z.number(),
  seatsAvailable: z.number(),
});

export type Preset = z.infer<typeof presetSchema>;
export type SenderPolicy = z.infer<typeof policySchema>;
export type ActionPolicy = SenderPolicy["actions"][string];
export type UsageRow = z.infer<typeof usageRowSchema>;
export type AccountDetails = z.infer<typeof detailsSchema>;
export type Overview = z.infer<typeof overviewSchema>;

/** The speeds the server applies for each preset: [increase by, every N days]. Custom uses each action's own numbers. */
export const PRESET_INFO: Record<Exclude<Preset, "off" | "custom">, { label: string; help: string }> = {
  conservative: { label: "Conservative", help: "Adds 1 to each limit every week." },
  balanced: { label: "Balanced", help: "Adds 2 to each limit every 2 to 3 days." },
  aggressive: { label: "Aggressive", help: "Adds 3 to each limit every day. Fastest, and the most likely to draw LinkedIn's attention." },
};

function parse<S extends z.ZodType>(schema: S, data: unknown): z.infer<S> {
  const result = schema.safeParse(data);
  if (!result.success) throw new ApiError(0, "The server sent a response Synex could not read. Try again.");
  return result.data;
}

export const managementService = {
  overview: async (): Promise<Overview> => parse(overviewSchema, await api.get("/linkedin-accounts/overview")),
  details: async (id: string): Promise<AccountDetails> => parse(detailsSchema, await api.get(`/linkedin-accounts/${id}/details`)),
  savePolicy: async (id: string, policy: SenderPolicy): Promise<SenderPolicy> => parse(policySchema, await api.put(`/linkedin-accounts/${id}/policy`, policy)),
  deactivate: async (id: string): Promise<void> => {
    await api.post(`/linkedin-accounts/${id}/deactivate`);
  },
};

export const detailKeys = { one: (id: string) => ["account-details", id] as const, overview: ["account-overview"] as const };

export const useOverview = () => useQuery({ queryKey: detailKeys.overview, queryFn: managementService.overview });

export const useAccountDetails = (id: string) =>
  useQuery({ queryKey: detailKeys.one(id), queryFn: () => managementService.details(id), retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 2 });

export function useManagementActions(id: string) {
  const qc = useQueryClient();
  return {
    savePolicy: useMutation({
      mutationFn: (policy: SenderPolicy) => managementService.savePolicy(id, policy),
      onSuccess: () => qc.invalidateQueries({ queryKey: detailKeys.one(id) }),
    }),
    deactivate: useMutation({
      mutationFn: () => managementService.deactivate(id),
      onSuccess: () => {
        void qc.invalidateQueries({ queryKey: detailKeys.one(id) });
        void qc.invalidateQueries({ queryKey: ["sender-accounts"] });
        void qc.invalidateQueries({ queryKey: detailKeys.overview });
      },
    }),
  };
}

/** Suggested starting limits for a new account: low, with a ceiling well under the hard maximum. Never above `ceiling`. */
const RECOMMENDED: Record<string, { daily: number; stop: number }> = {
  send_invite: { daily: 5, stop: 25 },
  send_message: { daily: 10, stop: 40 },
  visit_profile: { daily: 10, stop: 40 },
  follow_profile: { daily: 5, stop: 20 },
  check_connection: { daily: 20, stop: 60 },
  sync_inbox: { daily: 20, stop: 100 },
  sync_connections: { daily: 2, stop: 12 },
  collect_leads: { daily: 5, stop: 20 },
};

export function recommendedActions(usage: UsageRow[]): Record<string, ActionPolicy> {
  const out: Record<string, ActionPolicy> = {};
  for (const row of usage) {
    const rec = RECOMMENDED[row.action] ?? { daily: 5, stop: 20 };
    const stopAt = Math.min(rec.stop, row.ceiling);
    out[row.action] = { dailyLimit: Math.min(rec.daily, stopAt), increaseBy: 1, stopAt, intervalDays: 7, dynamicInterval: false };
  }
  return out;
}
