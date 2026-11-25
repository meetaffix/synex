import { z } from "zod";

export const accountStatusSchema = z.enum([
  "connected",
  "needs_reconnect",
  "restricted",
  "paused",
  "disconnected",
]);

export const syncModeSchema = z.enum(["all", "synex_only"]);

/** Hard per-account ceilings from the server config. No setting can go above them. */
export const ceilingsSchema = z.object({
  dailyActions: z.number(),
  connectionRequestsPerDay: z.number(),
  connectionRequestsPerWeek: z.number(),
  messagesPerDay: z.number(),
  profileVisitsPerDay: z.number(),
  followsPerDay: z.number(),
});

export const accountSchema = z.object({
  id: z.string(),
  name: z.string(),
  headline: z.string().nullable(),
  location: z.string().nullable().optional(),
  company: z.string().nullable().optional(),
  profileUrl: z.string().nullable(),
  avatarUrl: z.string().nullable(),
  status: accountStatusSchema,
  dailyActionLimit: z.number(),
  dailyActionsUsed: z.number(),
  dailyActionLimitToday: z.number().optional(),
  ceilings: ceilingsSchema,
  proxyConfigured: z.boolean(),
  syncMode: syncModeSchema,
  canChangeSyncMode: z.boolean(),
  pausedReason: z.string().nullable(),
  lastCheckedAt: z.string().nullable(),
  connectedAt: z.string().nullable(),
});
export const accountListSchema = z.array(accountSchema);

export const attemptStateSchema = z.enum([
  "starting",
  "awaiting_code",
  "awaiting_app_approval",
  "awaiting_manual_verification",
  "succeeded",
  "failed",
]);

export const attemptErrorCodeSchema = z.enum([
  "invalid_credentials",
  "timeout",
  "proxy_error",
  "proxy_required",
  "cancelled",
  "unknown",
]);

export const attemptSchema = z.object({
  attemptId: z.string(),
  state: attemptStateSchema,
  challenge: z
    .object({
      type: z.enum(["email_code", "sms_code", "authenticator_code"]),
      hint: z.string().nullish(),
    })
    .optional(),
  error: z
    .object({ code: attemptErrorCodeSchema, message: z.string() })
    .optional(),
  accountId: z.string().optional(),
});

export const reconnectLinkSchema = z.object({
  url: z.string(),
  expiresAt: z.string(),
});

export const reconnectInfoSchema = z.object({
  accountName: z.string(),
  avatarUrl: z.string().nullable(),
  expiresAt: z.string(),
});

export const proxyTestSchema = z.object({
  ok: z.boolean(),
  latencyMs: z.number().optional(),
  exitIp: z.string().optional(),
  country: z.string().optional(),
  error: z.object({ code: z.string(), message: z.string() }).optional(),
});

export type SyncMode = z.infer<typeof syncModeSchema>;
export type ProxyTestResult = z.infer<typeof proxyTestSchema>;
export type AccountStatus = z.infer<typeof accountStatusSchema>;
export type SenderAccount = z.infer<typeof accountSchema>;
export type Attempt = z.infer<typeof attemptSchema>;
export type AttemptErrorCode = z.infer<typeof attemptErrorCodeSchema>;
export type ReconnectLink = z.infer<typeof reconnectLinkSchema>;
export type ReconnectInfo = z.infer<typeof reconnectInfoSchema>;
