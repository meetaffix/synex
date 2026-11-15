import { api } from "@/services/client";

export interface AssistantSettings {
  available: boolean;
  enabled: boolean;
  monthlyMinuteCap: number;
  usedSeconds: number;
  remainingSeconds: number;
  capReached: boolean;
  idleTimeoutSeconds: number;
  historyEnabled: boolean;
  language: "en" | "en-IN";
  voice: string;
  model: string;
  month: string;
  canEdit: boolean;
}

export interface SessionInfo {
  ticket: string;
  wsPath: string;
  mode: "voice" | "text";
  language: string;
  idleTimeoutSeconds: number;
  remainingSeconds: number;
  agent: { model: string; voice: string; inputSampleRate: number; outputSampleRate: number; encoding: string };
  historyEnabled: boolean;
}

export type ProposalStatus = "pending" | "applied" | "cancelled" | "expired" | "failed";

export interface Proposal {
  id: string;
  tool: string;
  summary: string;
  changes: string[];
  status: ProposalStatus;
  needsRole: "member" | "manager" | "admin";
}

export interface PageContext {
  path: string;
  campaignId?: string;
  leadId?: string;
  field?: string;
}

export const assistantService = {
  settings: () => api.get<AssistantSettings>("/assistant/settings"),
  updateSettings: (patch: Partial<Pick<AssistantSettings, "enabled" | "monthlyMinuteCap" | "idleTimeoutSeconds" | "historyEnabled" | "language">>) =>
    api.put<AssistantSettings>("/assistant/settings", patch),
  startSession: (mode: "voice" | "text", page: PageContext) => api.post<SessionInfo>("/assistant/session", { mode, page }),
  confirm: (id: string) => api.post<Proposal>(`/assistant/proposals/${id}/confirm`),
  cancel: (id: string) => api.post<Proposal>(`/assistant/proposals/${id}/cancel`),
  clearHistory: () => api.delete<void>("/assistant/history"),
};
