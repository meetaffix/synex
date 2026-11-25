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
      <PageHeader title="Safety" description="Kill switch, hard limits and a record of every action."
        actions={<Button asChild variant="outline"><Link to="/settings">Back to settings</Link></Button>} />
      <KillSwitch />
      <Limits />
      <section aria-labelledby="audit-h" className="grid gap-2"><h2 id="audit-h" className="text-base font-semibold">Audit log</h2><p className="text-sm text-muted-foreground">Every action on LinkedIn, and every change to settings, is recorded.</p><div><Button asChild variant="outline"><Link to="/settings/audit">Open the audit log</Link></Button></div></section>
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
          <span className="text-xs text-muted-foreground">{(status.data?.workersActive ?? 0) > 0 ? "LinkedIn sending is running" : "LinkedIn sending is not running"}</span>
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
