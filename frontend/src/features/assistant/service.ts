import { api, postForBlob } from "@/services/client";

export interface AssistantSettings {
  available: boolean;
  enabled: boolean;
  monthlyMinuteCap: number;
  /** The plan this workspace is on and the most monthly minutes it includes. The server enforces it; this is only shown. */
  plan: string;
  planMinuteLimit: number;
  usedSeconds: number;
  remainingSeconds: number;
  capReached: boolean;
  idleTimeoutSeconds: number;
  historyEnabled: boolean;
  language: "en" | "en-IN";
  provider: "deepgram" | "local";
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

export interface ProviderPart { id: string; label: string; ready: boolean; detail: string }
export interface ProviderChoice { id: "deepgram" | "local"; label: string; cost: string; runs: string; licence: string; ready: boolean; detail: string; parts: ProviderPart[] }
export interface ChatCard { type: string; proposal?: Proposal; text?: string; label?: string; warnings?: string[] }

export const assistantService = {
  providers: () => api.get<{ selected: "deepgram" | "local"; providers: ProviderChoice[] }>("/assistant/providers"),
  localChat: (text: string, history: { role: string; content: string }[], page: PageContext) => api.post<{ reply: string; cards: ChatCard[] }>("/assistant/local/chat", { text, history, page }),
  transcribe: (audio: string) => api.post<{ text: string }>("/assistant/local/transcribe", { audio }),
  speak: (text: string) => postForBlob("/assistant/local/speak", { text }),
  settings: () => api.get<AssistantSettings>("/assistant/settings"),
  updateSettings: (patch: Partial<Pick<AssistantSettings, "enabled" | "monthlyMinuteCap" | "idleTimeoutSeconds" | "historyEnabled" | "language" | "provider">>) =>
    api.put<AssistantSettings>("/assistant/settings", patch),
  startSession: (mode: "voice" | "text", page: PageContext) => api.post<SessionInfo>("/assistant/session", { mode, page }),
  confirm: (id: string) => api.post<Proposal>(`/assistant/proposals/${id}/confirm`),
  cancel: (id: string) => api.post<Proposal>(`/assistant/proposals/${id}/cancel`),
  clearHistory: () => api.delete<void>("/assistant/history"),
};
