import { api } from "./client";
import type {
  User,
  AuthResponse,
  Lead,
  LeadList,
  Campaign,
  Conversation,
  Message,
  SentMessage,
  ComposeResult,
  Template,
  DashboardStats,
  ActivityItem,
  AnalyticsOverview,
  LeadStatus,
} from "@/types";

/*
 * The backend exposes a "resource gateway" API: one GET per resource for reads
 * and one POST per resource for writes, where the body's `action` field selects
 * the operation. These service helpers keep ergonomic, typed method names and
 * translate each into the right gateway call — so components/hooks are unchanged.
 */

/* ------------------------------- Auth --------------------------------- */
export const authService = {
  login: (data: { email: string; password: string }) =>
    api.post<AuthResponse>("/auth", { action: "login", ...data }),
  register: (data: { fullName: string; email: string; password: string }) =>
    api.post<AuthResponse>("/auth", { action: "register", ...data }),
  // Stateless JWT — logging out is purely client-side (discard the token).
  logout: () => api.post<{ok: boolean}>("/auth/logout"),
  me: () => api.get<User>("/auth/me"),
  updateProfile: (data: Partial<User>) => api.put<User>("/auth/me", data),
  forgotPassword: (email: string) =>
    api.post<{ ok: boolean }>("/auth", { action: "reset-request", email }),
  resetPassword: (token: string, password: string) =>
    api.post<{ ok: boolean }>("/auth", { action: "reset-confirm", token, password }),
};

/* ----------------------------- Dashboard ------------------------------ */
export interface DashboardData {
  stats: DashboardStats;
  activity: ActivityItem[];
}
export const dashboardService = {
  // One round-trip returns both headline stats and the activity feed.
  get: () => api.get<DashboardData>("/dashboard"),
};

/* ------------------------------ Leads --------------------------------- */
export interface LeadFilters {
  search?: string;
  status?: string;
  listId?: string;
}
function leadsQuery(f: LeadFilters = {}) {
  const p = new URLSearchParams();
  if (f.search) p.set("search", f.search);
  if (f.status) p.set("status", f.status);
  if (f.listId) p.set("listId", f.listId);
  const s = p.toString();
  return s ? `?${s}` : "";
}

export const leadsService = {
  list: (filters?: LeadFilters) =>
    api.get<Lead[]>(`/leads${leadsQuery(filters)}`),
  create: (data: Partial<Lead>) =>
    api.post<Lead>("/leads", { action: "create", ...data }),
  update: (id: string, data: Partial<Lead>) =>
    api.post<Lead>("/leads", { action: "update", id, ...data }),
  remove: (id: string) =>
    api.post<{ deleted: number }>("/leads", { action: "delete", ids: [id] }),
  bulkImport: (leads: Partial<Lead>[], listIds: string[]) =>
    api.post<{ created: number }>("/leads", { action: "bulk", leads, listIds }),
  // Delete ticked rows by id, or (deleteAll) everything matching the filters.
  bulkDelete: (ids: string[]) =>
    api.post<{ deleted: number }>("/leads", { action: "delete", ids }),
  deleteAll: (filters?: LeadFilters) =>
    api.post<{ deleted: number }>("/leads", {
      action: "delete",
      search: filters?.search,
      status: filters?.status,
      listId: filters?.listId,
    }),
  bulkStatus: (ids: string[], status: LeadStatus) =>
    api.post<{ updated: number }>("/leads", { action: "status", ids, status }),
  dedupe: () => api.post<{ merged: number }>("/leads", { action: "dedupe" }),
  importUrl: (source: string, sourceUrl: string, listIds: string[] = []) =>
    api.post<{ id: string; source: string; status: string; createdCount: number; detail: string }>(
      "/leads",
      { action: "import", source, sourceUrl, listIds }
    ),
  importSource: (data: {
    source: string;
    sourceUrl?: string;
    filters?: Record<string, string>;
    listIds?: string[];
  }) =>
    api.post<{ id: string; source: string; status: string; createdCount: number; detail: string }>(
      "/leads",
      { action: "import", ...data }
    ),
  review: (data: { urls?: string[]; rows?: Partial<Lead>[] }) =>
    api.post<ProspectReview>("/leads", { action: "review", ...data }),
  importJobs: () => api.get<ImportJob[]>("/leads/import"),
  enrich: (id: string) =>
    api.post<{ queued: boolean; detail: string }>("/leads", { action: "enrich", id }),
  enrichAll: () =>
    api.post<{ queued: number; detail: string }>("/leads", { action: "enrich-all" }),
};

export interface ImportJob {
  id: string;
  source: string;
  status: "pending" | "processing" | "completed" | "failed";
  createdCount: number;
  fetchedCount: number;
  totalCount: number | null;
  detail: string | null;
  createdAt: string;
}

export interface ReviewedProspect {
  firstName: string;
  lastName: string;
  company: string;
  jobTitle: string;
  linkedinUrl: string;
  location?: string | null;
  reason: "new" | "duplicate" | "already_contacted" | "invalid";
  valid: boolean;
}
export interface ProspectReview {
  total: number;
  valid: number;
  duplicates: number;
  alreadyContacted: number;
  invalid: number;
  prospects: ReviewedProspect[];
}

/* ---------------------------- Lead lists ------------------------------ */
export const leadListsService = {
  list: () => api.get<LeadList[]>("/lead-lists"),
  create: (data: Partial<LeadList>) =>
    api.post<LeadList>("/lead-lists", { action: "create", ...data }),
  update: (id: string, data: Partial<LeadList>) =>
    api.post<LeadList>("/lead-lists", { action: "update", id, ...data }),
  remove: (id: string) =>
    api.post<{ ok: boolean }>("/lead-lists", { action: "delete", id }),
};

/* ---------------------------- Campaigns ------------------------------- */
export interface MonitorTask {
  id: string;
  runId: string | null;
  type: string;
  status: string;
  attempts: number;
  leadId: string | null;
  leadName: string;
  error: string | null;
  createdAt: string | null;
  updatedAt: string | null;
}
export interface CampaignMonitor {
  campaignId: string;
  status: string;
  health: "ok" | "attention" | "failed";
  runCounts: Record<string, number>;
  currentActions: MonitorTask[];
  lastExecuted: MonitorTask | null;
  nextScheduled: {
    runId: string;
    leadId: string;
    leadName: string;
    stepOrder: number;
    at: string;
  } | null;
  failures: MonitorTask[];
  failedRuns: {
    runId: string;
    leadId: string;
    leadName: string;
    stepOrder: number;
    stoppedAt: string | null;
  }[];
  accounts: {
    id: string;
    name: string;
    live: boolean;
    dailyActionsUsed: number;
    dailyActionLimit: number | null;
  }[];
}

export const campaignsService = {
  list: () => api.get<Campaign[]>("/campaigns"),
  get: (id: string) => api.get<Campaign>(`/campaigns?id=${encodeURIComponent(id)}`),
  create: (data: Partial<Campaign>) =>
    api.post<Campaign>("/campaigns", { action: "create", ...data }),
  update: (id: string, data: Partial<Campaign>) =>
    api.post<Campaign>("/campaigns", { action: "update", id, ...data }),
  remove: (id: string) =>
    api.post<{ ok: boolean }>("/campaigns", { action: "delete", id }),
  monitor: (id: string) =>
    api.get<CampaignMonitor>(`/campaigns?id=${encodeURIComponent(id)}&monitor=1`),
  retryRun: (id: string, runId: string) =>
    api.post<{ ok: boolean }>("/campaigns", { action: "run", id, runId, runAction: "retry" }),
  skipRunStep: (id: string, runId: string) =>
    api.post<{ ok: boolean }>("/campaigns", { action: "run", id, runId, runAction: "skip" }),
};

/* -------------------------------- Team --------------------------------- */
export type TeamRole = "admin" | "manager" | "member";
export interface TeamMember {
  id: string;
  email: string;
  name: string | null;
  role: TeamRole;
  status: "invited" | "active";
  createdAt: string | null;
}
export interface TeamSeat {
  workspaceOwnerId: string;
  workspaceName: string;
  role: TeamRole;
  isOwner: boolean;
}
export interface TeamData {
  seat: TeamSeat;
  members: TeamMember[];
}
export const teamService = {
  // One GET returns the caller's seat and the member list together.
  get: () => api.get<TeamData>("/team"),
  invite: (email: string, role: TeamRole) =>
    api.post<TeamMember>("/team", { action: "invite", email, role }),
  updateRole: (id: string, role: TeamRole) =>
    api.post<TeamMember>("/team", { action: "update-role", memberId: id, role }),
  remove: (id: string) =>
    api.post<{ ok: boolean }>("/team", { action: "remove", memberId: id }),
};

/* -------------------------- Conversations ----------------------------- */
export interface ConversationFilters {
  status?: string;
  search?: string;
}
export const conversationsService = {
  list: (filters?: ConversationFilters) => {
    const p = new URLSearchParams();
    if (filters?.status) p.set("status", filters.status);
    if (filters?.search) p.set("search", filters.search);
    const s = p.toString();
    return api.get<Conversation[]>(`/conversations${s ? `?${s}` : ""}`);
  },
  messages: (id: string) =>
    api.get<Message[]>(`/conversations?conversationId=${encodeURIComponent(id)}`),
  sendMessage: (id: string, body: string) =>
    api.post<SentMessage>("/conversations", { action: "reply", conversationId: id, body }),
  compose: (leadId: string, body: string) =>
    api.post<ComposeResult>("/conversations", { action: "compose", leadId, body }),
  update: (id: string, data: Partial<Conversation>) =>
    api.post<Conversation>("/conversations", { action: "update", conversationId: id, ...data }),
};

/* ----------------------------- Templates ------------------------------ */
export const templatesService = {
  list: () => api.get<Template[]>("/templates"),
  create: (data: Partial<Template>) =>
    api.post<Template>("/templates", { action: "create", ...data }),
  update: (id: string, data: Partial<Template>) =>
    api.post<Template>("/templates", { action: "update", id, ...data }),
  remove: (id: string) =>
    api.post<{ ok: boolean }>("/templates", { action: "delete", id }),
};

/* ----------------------------- Analytics ------------------------------ */
export const analyticsService = {
  // Full payload — per-campaign performance is included under `.campaigns`.
  overview: () => api.get<AnalyticsOverview>("/analytics"),
};

/* ------------------------------ Settings ------------------------------ */
export interface Integration {
  provider: string;
  connected: boolean;
  config?: Record<string, unknown>;
}
export interface AppSettings {
  notificationPrefs: Record<string, boolean>;
  twoFactorEnabled: boolean;
  integrations: Integration[];
}
export const settingsService = {
  get: () => api.get<AppSettings>("/settings"),
  // One POST /settings handles every facet — `action` + the part that changed.
  updateNotifications: (prefs: Record<string, boolean>) =>
    api.post<AppSettings>("/settings", { action: "update", notificationPrefs: prefs }),
  updateTwoFactor: (enabled: boolean) =>
    api.post<AppSettings>("/settings", { action: "update", twoFactorEnabled: enabled }),
  changePassword: (currentPassword: string, newPassword: string) =>
    api.post<{ ok: boolean }>("/settings", {
      action: "change-password",
      currentPassword,
      newPassword,
    }),
  updateIntegration: (
    provider: string,
    connected: boolean,
    config?: Record<string, unknown>
  ) =>
    api.post<AppSettings>("/settings", {
      action: "update",
      integration: { provider, connected, config },
    }),
};

/* -------------------------------- AI ---------------------------------- */
export interface AIGenerateParams {
  stepType?: string;
  tone?: string;
  firstName?: string;
  company?: string;
  jobTitle?: string;
}
export const aiService = {
  generateMessage: (data: AIGenerateParams) =>
    api.post<{ body: string }>("/ai/generate-message", data),
};
