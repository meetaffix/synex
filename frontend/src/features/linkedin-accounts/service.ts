import type { z } from "zod";
import { api, ApiError } from "@/services/client";
import {
  accountListSchema,
  accountSchema,
  proxyTestSchema,
  attemptSchema,
  reconnectInfoSchema,
  reconnectLinkSchema,
  type Attempt,
  type ProxyTestResult,
  type SyncMode,
  type ReconnectInfo,
  type ReconnectLink,
  type SenderAccount,
} from "./schemas";

/** Where a connection attempt runs: the signed-in workspace or a public reconnect link. */
export type FlowScope = { kind: "account" } | { kind: "reconnect"; token: string };

export interface Credentials {
  /** An email address or a phone number with country code. */
  identifier: string;
  password: string;
  timezone?: string;
  proxyUrl?: string;
  syncMode?: SyncMode;
}

export interface AccountChanges {
  dailyActionLimit?: number;
  paused?: boolean;
  proxyUrl?: string | null;
  syncMode?: SyncMode;
}

function parse<S extends z.ZodType>(schema: S, data: unknown): z.infer<S> {
  const result = schema.safeParse(data);
  if (!result.success) {
    throw new ApiError(0, "The server sent a response Synex could not read. Try again.");
  }
  return result.data;
}

const attemptsPath = (scope: FlowScope) =>
  scope.kind === "account"
    ? "/linkedin-accounts/connect"
    : `/reconnect/${encodeURIComponent(scope.token)}/connect`;

export const senderAccountsService = {
  list: async (): Promise<SenderAccount[]> =>
    parse(accountListSchema, await api.get("/linkedin-accounts")),

  check: async (id: string): Promise<SenderAccount> =>
    parse(accountSchema, await api.post(`/linkedin-accounts/${id}/check`)),

  update: async (id: string, changes: AccountChanges): Promise<SenderAccount> =>
    parse(accountSchema, await api.patch(`/linkedin-accounts/${id}`, changes)),

  reconnectLink: async (id: string): Promise<ReconnectLink> =>
    parse(reconnectLinkSchema, await api.post(`/linkedin-accounts/${id}/reconnect-link`)),

  testProxy: async (proxyUrl: string): Promise<ProxyTestResult> =>
    parse(proxyTestSchema, await api.post("/linkedin-accounts/proxy-test", { proxyUrl })),

  disconnect: (id: string) => api.delete<void>(`/linkedin-accounts/${id}`),
};

export const connectService = {
  start: async (scope: FlowScope, credentials: Credentials): Promise<Attempt> => {
    const body =
      scope.kind === "account"
        ? credentials
        : { identifier: credentials.identifier, password: credentials.password };
    return parse(attemptSchema, await api.post(attemptsPath(scope), body));
  },

  get: async (scope: FlowScope, attemptId: string): Promise<Attempt> =>
    parse(attemptSchema, await api.get(`${attemptsPath(scope)}/${attemptId}`)),

  sendCode: async (scope: FlowScope, attemptId: string, code: string): Promise<Attempt> =>
    parse(attemptSchema, await api.post(`${attemptsPath(scope)}/${attemptId}/code`, { code })),

  cancel: (scope: FlowScope, attemptId: string) =>
    api.delete<void>(`${attemptsPath(scope)}/${attemptId}`),
};

export const reconnectService = {
  info: async (token: string): Promise<ReconnectInfo> =>
    parse(reconnectInfoSchema, await api.get(`/reconnect/${encodeURIComponent(token)}`)),
};
