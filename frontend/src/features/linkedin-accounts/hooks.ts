import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/services/client";
import { failureCopy, requestFailureMessage } from "./copy";
import {
  connectService,
  reconnectService,
  senderAccountsService,
  type AccountChanges,
  type Credentials,
  type FlowScope,
} from "./service";
import type { Attempt, AttemptErrorCode, SenderAccount } from "./schemas";

export const senderKeys = { list: ["sender-accounts"] as const };

export const POLL_INTERVAL_MS = 2000;

/** An attempt still running when the page is refreshed: only its id and start time are kept (never the credentials), so the dialog can resume it. */
const PENDING_KEY = "synex.connect-attempt";
export interface PendingAttempt { id: string; at: number }
export function pendingConnectAttempt(): PendingAttempt | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(PENDING_KEY) ?? "null") as PendingAttempt | null;
    return value && typeof value.id === "string" && typeof value.at === "number" ? value : null;
  } catch {
    return null;
  }
}
function rememberAttempt(value: PendingAttempt | null) {
  try {
    if (value) sessionStorage.setItem(PENDING_KEY, JSON.stringify(value));
    else sessionStorage.removeItem(PENDING_KEY);
  } catch {
    /* storage can be blocked: the flow still works, it just cannot resume */
  }
}

export const useSenderAccounts = () =>
  useQuery({ queryKey: senderKeys.list, queryFn: senderAccountsService.list });

export const useReconnectInfo = (token: string) =>
  useQuery({
    queryKey: ["reconnect-info", token],
    queryFn: () => reconnectService.info(token),
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 2,
    gcTime: 0,
  });

export function useAccountActions() {
  const qc = useQueryClient();
  const replace = (account: SenderAccount) =>
    qc.setQueryData<SenderAccount[]>(senderKeys.list, (accounts) =>
      accounts?.map((a) => (a.id === account.id ? account : a)),
    );
  return {
    check: useMutation({ mutationFn: senderAccountsService.check, onSuccess: replace }),
    // Changes may carry a proxy URL with credentials, so never keep them in the cache.
    update: useMutation({
      mutationFn: ({ id, changes }: { id: string; changes: AccountChanges }) =>
        senderAccountsService.update(id, changes),
      onSuccess: replace,
      gcTime: 0,
    }),
    reconnectLink: useMutation({ mutationFn: senderAccountsService.reconnectLink }),
    inviteLink: useMutation({
      mutationFn: senderAccountsService.inviteLink,
      onSuccess: () => void qc.invalidateQueries({ queryKey: ["sender-accounts"] }),
    }),
    disconnect: useMutation({
      mutationFn: senderAccountsService.disconnect,
      onSuccess: () => qc.invalidateQueries({ queryKey: senderKeys.list }),
    }),
  };
}

export type FlowView =
  | { kind: "form"; notice?: string }
  | { kind: "starting" }
  | { kind: "code"; challenge: NonNullable<Attempt["challenge"]>; error?: string }
  | { kind: "approval" }
  | { kind: "manual" }
  | { kind: "succeeded"; accountId?: string }
  | { kind: "failed"; code: AttemptErrorCode; message: string }
  | { kind: "lost"; message: string };

const isSettled = (state: Attempt["state"] | undefined) =>
  state === "succeeded" || state === "failed" || state === "awaiting_manual_verification";

function toView(attempt: Attempt, codeError: string | undefined): FlowView {
  switch (attempt.state) {
    case "awaiting_code":
      return {
        kind: "code",
        challenge: attempt.challenge ?? { type: "email_code" },
        error: attempt.error?.message ?? codeError,
      };
    case "awaiting_app_approval":
      return { kind: "approval" };
    case "awaiting_manual_verification":
      return { kind: "manual" };
    case "succeeded":
      return { kind: "succeeded", accountId: attempt.accountId };
    case "failed":
      return {
        kind: "failed",
        code: attempt.error?.code ?? "unknown",
        message: attempt.error?.message ?? failureCopy.unknown.detail,
      };
    default:
      return { kind: "starting" };
  }
}

/**
 * Drives one connection attempt. Passwords are only ever function arguments: they are
 * never kept in state, in the query cache or in a mutation. Polling stops once the
 * attempt settles or the component unmounts, and an unfinished attempt is cancelled
 * when the flow goes away.
 */
export function useConnectFlow(scope: FlowScope) {
  const qc = useQueryClient();
  const [pending] = useState(() => (scope.kind === "account" ? pendingConnectAttempt() : null));
  const [attemptId, setAttemptId] = useState<string | null>(pending?.id ?? null);
  const [startedAt, setStartedAt] = useState<number | null>(pending?.at ?? null);
  const [starting, setStarting] = useState(false);
  const [notice, setNotice] = useState<string>();
  const [codeError, setCodeError] = useState<string>();
  const queryKey = ["connect-attempt", scope.kind, attemptId] as const;

  const attempt = useQuery({
    queryKey,
    queryFn: () => connectService.get(scope, attemptId as string),
    enabled: attemptId !== null,
    refetchInterval: (query) => (isSettled(query.state.data?.state) ? false : POLL_INTERVAL_MS),
    gcTime: 0,
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 2,
  });

  const latest = useRef({ scope, attemptId, state: attempt.data?.state });
  latest.current = { scope, attemptId, state: attempt.data?.state };
  const cancelled = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const cancel = useCallback(() => {
    const { scope: current, attemptId: id, state } = latest.current;
    if (id === null || isSettled(state) || cancelled.current) return;
    cancelled.current = true;
    rememberAttempt(null);
    connectService.cancel(current, id).catch(() => undefined);
  }, []);

  useEffect(() => cancel, [cancel]);

  const gone = attempt.error instanceof ApiError && attempt.error.status === 404;
  const finished = isSettled(attempt.data?.state) || gone;
  useEffect(() => {
    if (finished) rememberAttempt(null);
  }, [finished]);

  const succeeded = attempt.data?.state === "succeeded";
  useEffect(() => {
    if (succeeded) void qc.invalidateQueries({ queryKey: senderKeys.list });
  }, [succeeded, qc]);

  const start = async (credentials: Credentials) => {
    setNotice(undefined);
    setStarting(true);
    try {
      const created = await connectService.start(scope, credentials);
      if (!mounted.current) {
        // The dialog closed while the request was in flight: don't leave the attempt running.
        connectService.cancel(scope, created.attemptId).catch(() => undefined);
        return;
      }
      cancelled.current = false;
      const now = Date.now();
      setStartedAt(now);
      if (scope.kind === "account") rememberAttempt({ id: created.attemptId, at: now });
      qc.setQueryData(["connect-attempt", scope.kind, created.attemptId], created);
      setAttemptId(created.attemptId);
    } catch (error) {
      setNotice(requestFailureMessage(error));
    } finally {
      setStarting(false);
    }
  };

  const sendCode = async (code: string) => {
    if (attemptId === null) return;
    setCodeError(undefined);
    try {
      await qc.cancelQueries({ queryKey });
      qc.setQueryData(queryKey, await connectService.sendCode(scope, attemptId, code));
    } catch (error) {
      setCodeError(requestFailureMessage(error));
    }
  };

  const reset = () => {
    qc.removeQueries({ queryKey });
    rememberAttempt(null);
    setStartedAt(null);
    setAttemptId(null);
    setNotice(undefined);
    setCodeError(undefined);
  };

  let view: FlowView;
  if (attemptId === null) {
    view = starting ? { kind: "starting" } : { kind: "form", notice };
  } else if (attempt.data && !(attempt.isError && !isSettled(attempt.data.state))) {
    view = toView(attempt.data, codeError);
  } else if (attempt.isError) {
    view = gone
      ? { kind: "failed", code: "unknown", message: failureCopy.gone }
      : { kind: "lost", message: requestFailureMessage(attempt.error) };
  } else {
    view = { kind: "starting" };
  }

  return { view, startedAt, start, sendCode, cancel, reset, retryPolling: () => void attempt.refetch() };
}
