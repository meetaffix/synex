import { api } from "./client";
import type {
  User,
  AuthResponse,
  Lead,
  LeadList,
  Template,
  DashboardStats,
  ActivityItem,
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
  review: (data: { urls?: string[]; rows?: Partial<Lead>[] }) =>
    api.post<ProspectReview>("/leads", { action: "review", ...data }),
  importJobs: () => api.get<ImportJob[]>("/leads/import"),
  enrich: (id: string) =>
    api.post<{ queued: boolean; detail: string }>("/leads", { action: "enrich", id }),
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
