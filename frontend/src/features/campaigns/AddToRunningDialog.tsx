import { useQuery } from "@tanstack/react-query";
import { api } from "@/services/client";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";

interface Detail { name: string; accountName: string; steps: { type: string; message: string | null; order: number }[] }

/** A running campaign starts a new person's sequence straight away. This shows the first message they would get, so the yes is an informed one. */
export function AddToRunningDialog({ open, onOpenChange, campaignId, leadName, loading, onConfirm }: {
  open: boolean; onOpenChange: (open: boolean) => void; campaignId: string; leadName: string; loading?: boolean; onConfirm: () => void;
}) {
  const campaign = useQuery({ queryKey: ["add-confirm", campaignId], enabled: open, queryFn: () => api.get<Detail>(`/campaigns?id=${campaignId}`), staleTime: 0 });
  const steps = [...(campaign.data?.steps ?? [])].sort((a, b) => a.order - b.order);
  const first = steps.find((s) => !["wait", "end", "if_connected", "if_active"].includes(s.type));
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Add {leadName} to a running campaign?</DialogTitle>
          <DialogDescription>{campaign.data ? `"${campaign.data.name}" is sending now, so ${leadName}'s sequence starts straight away, inside the sender's limits and working hours.` : "This campaign is sending now."}</DialogDescription>
        </DialogHeader>
        {campaign.isLoading && <Skeleton className="h-16 w-full" />}
        {campaign.data && (
          <div className="grid gap-2 rounded-lg border border-border bg-surface-muted p-3 text-sm">
            <p className="font-medium">First step: {first ? first.type.replaceAll("_", " ") : "none"} <span className="font-normal text-muted-foreground">from {campaign.data.accountName || "no sender"}</span></p>
            {first?.message && <p className="whitespace-pre-wrap rounded-md bg-surface p-2">{first.message}</p>}
            {first?.message && <p className="text-xs text-muted-foreground">Names and other variables are filled in for each person when it is sent.</p>}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={onConfirm} loading={loading} disabled={!campaign.data}>Yes, add and start</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
