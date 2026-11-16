import { z } from "zod";
import { api, ApiError } from "@/services/client";

export type DateRange = "all" | "7d" | "30d" | "90d";
export type Granularity = "week" | "day";

export interface DashboardFilters {
  range: DateRange;
  campaignId: string;
  accountId: string;
}

export const summarySchema = z.object({
  connectionsAccepted: z.number(),
  leadsContacted: z.number(),
  replies: z.number(),
  interestedLeads: z.number(),
  interestedAnswered: z.number(),
  medianResponseSeconds: z.number().nullable(),
});

export const seriesSchema = z.object({
  points: z.array(z.object({ date: z.string(), requests: z.number(), accepted: z.number(), replies: z.number() })),
});

export const accountStatsSchema = z.array(
  z.object({
    accountId: z.string(),
    requestsSent: z.number(),
    acceptedPercent: z.number(),
    leadsContacted: z.number(),
    replyPercent: z.number(),
  }),
);

export const funnelSchema = z.object({ stages: z.array(z.object({ key: z.string(), label: z.string(), count: z.number(), percentOfPrevious: z.number().nullable() })) });
export const campaignTableSchema = z.array(z.object({
  campaignId: z.string(), name: z.string(), status: z.string(), leads: z.number(), contacted: z.number(), accepted: z.number(), replied: z.number(), interested: z.number(),
  acceptedPercent: z.number().nullable(), replyPercent: z.number().nullable(),
}));

export type Summary = z.infer<typeof summarySchema>;
export type Series = z.infer<typeof seriesSchema>;
export type AccountStats = z.infer<typeof accountStatsSchema>;

/** A dashboard feed either exists on the server or does not yet. */
export type Feed<T> = { state: "ready"; data: T } | { state: "unavailable" };

const DAYS: Record<Exclude<DateRange, "all">, number> = { "7d": 7, "30d": 30, "90d": 90 };

function query(filters: DashboardFilters, extra: Record<string, string> = {}): string {
  const params = new URLSearchParams(extra);
  if (filters.range !== "all") {
    params.set("from", new Date(Date.now() - DAYS[filters.range] * 86_400_000).toISOString());
    params.set("to", new Date().toISOString());
  }
  if (filters.campaignId) params.set("campaignId", filters.campaignId);
  if (filters.accountId) params.set("accountId", filters.accountId);
  const text = params.toString();
  return text ? `?${text}` : "";
}

async function feed<S extends z.ZodType>(schema: S, path: string): Promise<Feed<z.infer<S>>> {
  let raw: unknown;
  try {
    raw = await api.get(path);
  } catch (error) {
    if (error instanceof ApiError && [404, 405, 501].includes(error.status)) return { state: "unavailable" };
    throw error;
  }
  const result = schema.safeParse(raw);
  if (!result.success) throw new ApiError(0, "The server sent a response Synex could not read. Try again.");
  return { state: "ready", data: result.data };
}

/**
 * These endpoints are not mounted on the API yet; until they are, each call resolves to
 * "unavailable" and the dashboard says so instead of showing numbers.
 */
export const dashboardService = {
  summary: (filters: DashboardFilters) => feed(summarySchema, `/dashboard/summary${query(filters)}`),
  timeseries: (filters: DashboardFilters, granularity: Granularity) =>
    feed(seriesSchema, `/dashboard/timeseries${query(filters, { granularity })}`),
  accounts: (filters: DashboardFilters) => feed(accountStatsSchema, `/dashboard/accounts${query(filters)}`),
  funnel: (filters: DashboardFilters) => feed(funnelSchema, `/dashboard/funnel${query(filters)}`),
  campaigns: (filters: DashboardFilters) => feed(campaignTableSchema, `/dashboard/campaigns${query(filters)}`),
};

/** The same filters as the screen, for an export. */
export const exportQuery = (filters: DashboardFilters, kind: string) => query(filters, { kind });
