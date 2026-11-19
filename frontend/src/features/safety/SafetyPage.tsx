import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/features/auth/AuthContext";
import { requestFailureMessage } from "@/features/linkedin-accounts/copy";
import { api, ApiError } from "@/services/client";
import { formatRelative } from "@/utils/format";

interface Ceilings { daily: { action: string; label: string; ceiling: number }[]; dailyTotal: number; weeklyInvites: number; newAccountDailyLimit: number; testProfile: Record<string, number> }
interface Status { killSwitch: boolean; forcedBySetting: boolean; workersActive: number }
interface AuditItem { id: string; at: string; account: string; action: string; result: string | null; status: string; reason: string | null; person: string | null; campaign: string | null }
interface Audit { items: AuditItem[]; total: number; limit: number; offset: number; note: string }
interface Account { id: string; name: string }

const PAGE = 25;
const ACTION_NAMES: Record<string, string> = {
  send_invite: "Connection request", send_message: "Message", visit_profile: "Profile view", follow_profile: "Follow", check_connection: "Connection check",
  sync_inbox: "Inbox read", withdraw_invite: "Invitation withdrawn", sync_connections: "Connection list read", collect_leads: "Lead collection",
  like_post: "Post like", send_inmail: "InMail", send_voice_note: "Voice note", engage_post: "Reaction or comment",
};

/** Everything that keeps senders safe, in one place: the stop button, the limits nothing can raise, and a record of every action taken. */
export function SafetyPage() {
  return (
    <div className="grid grid-cols-1 gap-8">
      <PageHeader title="Safety" description="The kill switch, the hard limits no setting can raise, and a record of every action Synex took on LinkedIn."
        actions={<Button asChild variant="outline"><Link to="/settings">Back to settings</Link></Button>} />
      <KillSwitch />
      <Limits />
      <AuditLog />
    </div>
  );
}

function KillSwitch() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const admin = !!user?.isAdmin;
  const [confirm, setConfirm] = useState<boolean | null>(null);
  const status = useQuery({ queryKey: ["safety", "status"], queryFn: () => api.get<Status>("/outreach/status"), enabled: admin, retry: false });
  const set = useMutation({
    mutationFn: (enabled: boolean) => api.post<Status>("/outreach/kill-switch", { enabled }),
    onSuccess: (next) => { qc.setQueryData(["safety", "status"], next); toast.success(next.killSwitch ? "All sending is stopped." : "Sending can resume."); setConfirm(null); },
    onError: (e) => toast.error(requestFailureMessage(e)),
  });
  const on = status.data?.killSwitch ?? false;
  return (
    <section aria-labelledby="kill-h" className="grid max-w-3xl gap-3 rounded-lg border border-border bg-surface p-4">
      <h2 id="kill-h" className="text-base font-semibold">Kill switch</h2>
      <p className="text-sm text-muted-foreground">Stops every action on LinkedIn for every workspace on this server at once. Workers check it before each action, so an action already in the browser finishes and nothing new starts.</p>
      {!admin ? (
        <p role="note" className="text-sm">Only a platform administrator can use the kill switch. If something looks wrong, pause the sender or the campaign instead, or ask your administrator.</p>
      ) : status.isLoading ? (
        <Skeleton className="h-10 w-64" aria-label="Loading the kill switch" />
      ) : status.isError ? (
        <p role="alert" className="text-sm text-danger">The kill switch status could not be read. {status.error instanceof ApiError ? status.error.message : ""}</p>
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          <p role="status" className={on ? "font-semibold text-danger" : "font-medium"}>{on ? "Stopped: nothing is sent." : "Running: senders act within their limits."}</p>
          {status.data?.forcedBySetting && <p className="text-xs text-muted-foreground">Forced on by the server setting OUTREACH_KILL_SWITCH; it cannot be turned off here.</p>}
          <Button variant={on ? "outline" : "destructive"} disabled={status.data?.forcedBySetting} onClick={() => setConfirm(!on)}>{on ? "Resume sending" : "Stop all sending now"}</Button>
          <span className="text-xs text-muted-foreground">{status.data?.workersActive ?? 0} worker{status.data?.workersActive === 1 ? "" : "s"} running</span>
        </div>
      )}
      <Dialog open={confirm !== null} onOpenChange={(open) => !open && setConfirm(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{confirm ? "Stop all sending?" : "Resume sending?"}</DialogTitle>
            <DialogDescription>{confirm ? "Every sender on this server stops before its next action. Campaigns keep their place and continue when you resume." : "Senders continue where they stopped, within their daily limits."}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirm(null)}>Cancel</Button>
            <Button variant={confirm ? "destructive" : "default"} loading={set.isPending} onClick={() => confirm !== null && set.mutate(confirm)}>{confirm ? "Stop all sending" : "Resume sending"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}

function Limits() {
  const limits = useQuery({ queryKey: ["safety", "ceilings"], queryFn: () => api.get<Ceilings>("/outreach/ceilings"), retry: false });
  return (
    <section aria-labelledby="limits-h" className="grid max-w-3xl gap-3">
      <h2 id="limits-h" className="text-base font-semibold">Hard limits</h2>
      <p className="text-sm text-muted-foreground">Per sender account, per day, whatever a campaign or a setting says. A daily limit of 0 means stopped, and a new account starts at 0.</p>
      {limits.isLoading && <Skeleton className="h-48 w-full" aria-label="Loading the limits" />}
      {limits.isError && <p role="alert" className="text-sm text-danger">The limits could not be loaded.</p>}
      {limits.data && (
        <>
          <p className="text-sm"><span className="font-medium">{limits.data.dailyTotal}</span> actions a day in total, and <span className="font-medium">{limits.data.weeklyInvites}</span> connection requests in any seven days.</p>
          <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Hard limits per action (scrolls sideways)">
            <table className="w-full min-w-[28rem] text-sm">
              <caption className="sr-only">Hard daily limit and test profile for each action</caption>
              <thead><tr className="text-left text-muted-foreground"><th scope="col" className="py-2 pr-3 font-medium">Action</th><th scope="col" className="py-2 pr-3 font-medium">Hard daily limit</th><th scope="col" className="py-2 font-medium">Test profile</th></tr></thead>
              <tbody>
                {limits.data.daily.map((row) => (
                  <tr key={row.action} className="border-t border-border"><th scope="row" className="py-2 pr-3 text-left font-normal">{row.label}</th><td className="py-2 pr-3">{row.ceiling}</td><td className="py-2">{limits.data.testProfile[row.action] || "stopped"}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-muted-foreground">The test profile is for a test account: 5 profile views, 5 connection requests and 5 messages a day, with random gaps. Apply it from a sender&apos;s Sender limits tab.</p>
        </>
      )}
    </section>
  );
}

function AuditLog() {
  const [offset, setOffset] = useState(0);
  const [accountId, setAccountId] = useState("");
  const accounts = useQuery({ queryKey: ["sender-accounts"], queryFn: () => api.get<Account[]>("/linkedin-accounts"), retry: false });
  const log = useQuery({ queryKey: ["safety", "audit", offset, accountId], queryFn: () => api.get<Audit>(`/outreach/audit?limit=${PAGE}&offset=${offset}${accountId ? `&accountId=${accountId}` : ""}`), retry: false });
  const data = log.data;
  return (
    <section aria-labelledby="audit-h" className="grid gap-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h2 id="audit-h" className="text-base font-semibold">Audit log</h2><p className="text-sm text-muted-foreground">Every action on LinkedIn, newest first, with why it ended the way it did.</p></div>
        <div className="grid gap-1">
          <label htmlFor="audit-account" className="text-sm font-medium">Sender</label>
          <NativeSelect id="audit-account" className="w-auto" value={accountId} onChange={(e) => { setAccountId(e.target.value); setOffset(0); }}>
            <option value="">All senders</option>
            {(accounts.data ?? []).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </NativeSelect>
        </div>
      </div>
      {log.isLoading && <Skeleton className="h-40 w-full" aria-label="Loading the audit log" />}
      {log.isError && <div role="alert" className="flex flex-wrap items-center gap-3 text-sm text-danger">The audit log could not be loaded. <Button size="sm" variant="outline" onClick={() => void log.refetch()}>Try again</Button></div>}
      {data && data.items.length === 0 && <p className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">No actions yet. Once a campaign runs, each action appears here.</p>}
      {data && data.items.length > 0 && (
        <>
          <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Audit log (scrolls sideways)">
            <table className="w-full min-w-[44rem] text-sm">
              <caption className="sr-only">Actions taken on LinkedIn</caption>
              <thead><tr className="text-left text-muted-foreground">{["When", "Sender", "Action", "Person", "Campaign", "Outcome"].map((h) => <th key={h} scope="col" className="py-2 pr-3 font-medium">{h}</th>)}</tr></thead>
              <tbody>
                {data.items.map((i) => (
                  <tr key={i.id} className="border-t border-border align-top">
                    <td className="py-2 pr-3"><time dateTime={i.at} title={i.at}>{formatRelative(i.at)}</time></td>
                    <td className="py-2 pr-3">{i.account}</td>
                    <th scope="row" className="py-2 pr-3 text-left font-normal">{ACTION_NAMES[i.action] ?? i.action}</th>
                    <td className="py-2 pr-3">{i.person ?? "-"}</td>
                    <td className="py-2 pr-3">{i.campaign ?? "-"}</td>
                    <td className={i.status === "ok" ? "py-2" : "py-2 text-danger"}>{i.reason ?? i.result ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <span role="status">{offset + 1} to {Math.min(offset + PAGE, data.total)} of {data.total}</span>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Newer</Button>
              <Button size="sm" variant="outline" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>Older</Button>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">{data.note}</p>
        </>
      )}
    </section>
  );
}
