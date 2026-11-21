import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/services/client";
import { requestFailureMessage } from "@/features/linkedin-accounts/copy";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";

interface Planned { leadName: string; accountName: string | null; stepType: string | null; message: string; earliestAt: string | null; skipReason: string | null }

/** The answer to "who does this send to, and what exactly?" for anything that can start a real message after the first launch. Nothing here sends: the
 *  list comes from the campaign's dry run, and the button is the person's own yes. */
export function SendConfirmDialog({ open, onOpenChange, campaignId, title, intro, confirmLabel, loading, onConfirm, onlyLead }: {
  open: boolean; onOpenChange: (open: boolean) => void; campaignId: string; title: string; intro: string; confirmLabel: string; loading?: boolean;
  onConfirm: () => void; onlyLead?: string;
}) {
  const plan = useQuery({
    queryKey: ["send-confirm", campaignId, open],
    enabled: open,
    queryFn: async () => (await api.post<{ actions: Planned[] }>(`/campaigns/${campaignId}/dry-run`)).actions,
    staleTime: 0,
  });
  const all = (plan.data ?? []).filter((a) => !onlyLead || a.leadName === onlyLead);
  const sends = all.filter((a) => !a.skipReason);
  const shown = sends.slice(0, 5);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{intro}</DialogDescription>
        </DialogHeader>
        {plan.isLoading && <Skeleton className="h-24 w-full" />}
        {plan.isError && <p role="alert" className="text-sm text-danger">{plan.error instanceof ApiError ? plan.error.message : requestFailureMessage(plan.error)} Without the list of who is sent to, there is nothing to confirm.</p>}
        {plan.data && (
          <div className="grid gap-3 text-sm" data-testid="send-confirm-list">
            {shown.length === 0 && <p className="rounded-lg border border-border bg-surface-muted p-3">Nothing would be sent right now. {all.find((a) => a.skipReason)?.skipReason ?? ""}</p>}
            {shown.map((a, i) => (
              <div key={i} className="grid gap-1 rounded-lg border border-border bg-surface-muted p-3">
                <p className="font-medium">{a.leadName} <span className="font-normal text-muted-foreground">from {a.accountName ?? "no sender"}</span></p>
                <p className="text-muted-foreground">{a.stepType?.replaceAll("_", " ")}{a.earliestAt ? `, not before ${new Date(a.earliestAt).toLocaleString()}` : ""}</p>
                {a.message && <p className="whitespace-pre-wrap rounded-md bg-surface p-2">{a.message}</p>}
              </div>
            ))}
            {sends.length > shown.length && <p className="text-muted-foreground">and {sends.length - shown.length} more.</p>}
          </div>
        )}
        <DialogFooter className="mt-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={onConfirm} loading={loading} disabled={!plan.data}>{confirmLabel}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
