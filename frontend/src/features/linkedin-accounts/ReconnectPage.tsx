import { useMemo, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import { Illustration } from "@/components/brand/Illustration";
import { UserAvatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Logo } from "@/components/shared/Logo";
import { ApiError } from "@/services/client";
import { formatDate } from "@/utils/format";
import { ConnectFlow } from "./ConnectFlow";
import { requestFailureMessage } from "./copy";
import { useReconnectInfo } from "./hooks";
import type { FlowScope } from "./service";

/** Public page opened from a single-use reconnect link. No signed-in session is involved. */
export function ReconnectPage() {
  const { token = "" } = useParams();
  const info = useReconnectInfo(token);
  const scope = useMemo<FlowScope>(() => ({ kind: "reconnect", token }), [token]);

  return (
    <div className="min-h-dvh bg-background px-4 py-8 sm:py-16">
      <div className="mx-auto grid max-w-md gap-6">
        <Logo />
        <main className="grid gap-6 rounded-lg border border-border bg-surface p-4 shadow-raised sm:p-6">
          {info.isLoading && <LoadingState />}
          {info.isError && <LinkProblem error={info.error} onRetry={() => void info.refetch()} />}
          {info.data && (
            <>
              <header className="flex items-center gap-4">
                <UserAvatar name={info.data.accountName} src={info.data.avatarUrl} className="size-12" />
                <div className="min-w-0">
                  <h1 className="text-xl font-semibold">Reconnect {info.data.accountName}</h1>
                  <p className="text-sm text-muted-foreground">
                    Sign in to LinkedIn so Synex can keep sending from this account. This link works once and expires
                    on {formatDate(info.data.expiresAt)}.
                  </p>
                </div>
              </header>
              <ConnectFlow scope={scope} />
            </>
          )}
        </main>
      </div>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="grid gap-4" role="status" aria-label="Checking the reconnect link">
      <Skeleton className="h-12 w-3/4" />
      <Skeleton className="h-9 w-full" />
      <Skeleton className="h-9 w-full" />
    </div>
  );
}

function LinkProblem({ error, onRetry }: { error: Error; onRetry: () => void }): ReactNode {
  const expired = error instanceof ApiError && error.status === 404;
  return (
    <div className="grid justify-items-center gap-4 text-center">
      <Illustration name="error" />
      <h1 className="text-xl font-semibold">
        {expired ? "This link has expired or was already used" : "Synex could not check this link"}
      </h1>
      <p className="text-sm text-muted-foreground">
        {expired
          ? "Reconnect links work once and last 24 hours. Ask the person who shared it for a new link."
          : requestFailureMessage(error)}
      </p>
      {!expired && (
        <div>
          <Button variant="secondary" onClick={onRetry}>
            Try again
          </Button>
        </div>
      )}
    </div>
  );
}
