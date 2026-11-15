import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { Linkedin, Plus, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { api } from "@/services/client";
import {
  useAccounts,
  useRefresh,
  statusLabel,
  formatDate,
  type Account,
} from "./data";
import { Header, Status, Notice, Empty, Load, Profile } from "./shared";

export function AccountsPage() {
  const accounts = useAccounts(),
    refresh = useRefresh();
  const previous = useQuery({
    queryKey: ["publishing", "previous-profiles"],
    queryFn: () =>
      api.get<{ id: string; name: string }[]>("/linkedin/previous-profiles"),
  });
  const [busy, setBusy] = useState("");
  const [disconnect, setDisconnect] = useState<Account | null>(null);
  const [params, setParams] = useSearchParams();
  const connect = async (targetId?: string) => {
    setBusy("connect");
    try {
      const r = await api.post<{ url: string }>(
        "/linkedin/connect",
        targetId ? { accountId: targetId } : {},
      );
      window.location.assign(r.url);
    } catch (e) {
      toast.error((e as Error).message);
      setBusy("");
    }
  };
  const run = async (a: Account, action: string) => {
    setBusy(a.id);
    try {
      await api.post(`/linkedin/accounts/${a.id}/${action}`);
      await refresh();
      toast.success(
        action === "check" ? "Connection verified" : "Connection removed",
      );
      setDisconnect(null);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy("");
    }
  };
  useEffect(() => {
    if (params.has("linkedin") && accounts.isFetched) {
      const verified =
        params.get("linkedin") === "connected" &&
        accounts.data?.some(
          (a) => a.id === params.get("account") && a.status === "connected",
        );
      toast[verified ? "success" : "error"](
        verified
          ? "LinkedIn connected"
          : "Authorization could not be confirmed. Check your account and try again.",
      );
      setParams({}, { replace: true });
    }
  }, [params, setParams, accounts.isFetched, accounts.data]);
  return (
    <>
      <Header
        title="Publishing connections"
        description="Your authorized profiles, permissions, and connection health."
        action={
          <Button loading={busy === "connect"} onClick={() => connect()}>
            <Plus />
            Connect LinkedIn
          </Button>
        }
      />
      <Load error={accounts.error} loading={accounts.isLoading} />
      {accounts.data?.length === 0 && (
        <Empty title="No LinkedIn accounts connected">
          <p>
            Authorize securely on LinkedIn. Your password stays with LinkedIn.
          </p>
          <Button onClick={() => connect()} loading={!!busy}>
            <Linkedin />
            Connect your account
          </Button>
        </Empty>
      )}
      {accounts.data?.map((a) => (
        <section className="connection-section" key={a.id}>
          <div className="connection-header">
            <Profile account={a} />
            <Status value={a.status} />
            <div className="inline-actions">
              <Button
                variant="outline"
                loading={busy === a.id}
                disabled={a.status !== "connected"}
                onClick={() => run(a, "check")}
              >
                Check connection
              </Button>
              <Button
                variant="outline"
                disabled={!!busy}
                onClick={() => connect(a.id)}
              >
                Reconnect
              </Button>
              <Button variant="ghost" onClick={() => setDisconnect(a)}>
                Disconnect
              </Button>
            </div>
          </div>
          <div className="connection-details">
            <div>
              <span>Last verified</span>
              <strong>{formatDate(a.checkedAt)}</strong>
            </div>
            <div>
              <span>Authorization expires</span>
              <strong>{formatDate(a.expiresAt)}</strong>
            </div>
            <div>
              <span>Granted permissions</span>
              <strong>{a.scopes.join(", ") || "None"}</strong>
            </div>
          </div>
          <div className="capability-list">
            {Object.entries(a.capabilities).map(([key, value]) => (
              <div key={key}>
                <span>
                  {key === "connections" ? "Connection requests" : key}
                </span>
                <span className={value === "available" ? "positive" : "muted"}>
                  {statusLabel(value)}
                </span>
              </div>
            ))}
          </div>
          {a.capabilities.publishing !== "available" && (
            <Notice>
              Publishing needs an active connection and the Share on LinkedIn
              product permission. Enable the product for your developer app,
              then reconnect.
            </Notice>
          )}
        </section>
      ))}
      {!!previous.data?.length && (
        <section className="section">
          <div className="section-heading">
            <h2>Previous profiles</h2>
            <span>From your earlier workspace</span>
          </div>
          <p className="footnote">
            These saved records do not have official publishing authorization.
            Use Connect LinkedIn to authorize a profile.
          </p>
          {previous.data.map((p) => (
            <div className="diagnostic-row" key={p.id}>
              <span>{p.name}</span>
              <Status value="requires_authorization" />
            </div>
          ))}
        </section>
      )}
      <div className="footnote">
        Signing into Synex and authorizing publishing are separate permissions.
        Messaging and connection requests are manual workflows in this app.
      </div>
      <Dialog
        open={!!disconnect}
        onOpenChange={(open) => !open && setDisconnect(null)}
      >
        <DialogContent>
          <DialogTitle>Disconnect {disconnect?.name}?</DialogTitle>
          <DialogDescription>
            Stored publishing credentials will be removed and pending posts
            paused. Drafts and publishing history will be kept. LinkedIn sign-in
            remains available.
          </DialogDescription>
          <div className="dialog-actions">
            <Button variant="outline" onClick={() => setDisconnect(null)}>
              Keep connection
            </Button>
            <Button
              variant="destructive"
              loading={!!busy}
              onClick={() => disconnect && run(disconnect, "disconnect")}
            >
              Disconnect
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
