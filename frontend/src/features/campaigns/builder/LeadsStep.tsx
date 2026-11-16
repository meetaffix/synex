import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { AddLeadsDialog } from "@/features/leads/components/AddLeadsDialog";
import { leadListsService } from "@/services/resources";
import type { BuilderState } from "./model";

/** Step 2. Moving on with no leads is allowed; the launch checklist says so. */
export function LeadsStep({ state, set }: { state: BuilderState; set: (change: Partial<BuilderState>) => void }) {
  const lists = useQuery({ queryKey: ["lead-lists"], queryFn: leadListsService.list });
  const [adding, setAdding] = useState(false);
  const chosen = lists.data?.find((l) => l.id === state.leadListId);

  return (
    <section aria-labelledby="leads-h" className="grid grid-cols-1 gap-4">
      <div>
        <h2 id="leads-h" className="text-lg font-semibold">List of leads</h2>
        <p className="text-sm text-muted-foreground">Choose the saved list this campaign contacts, or add leads from LinkedIn, a CSV, a Google Sheet or your own connections.</p>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <div className="grid min-w-0 gap-1">
          <Label htmlFor="campaign-list">Lead list</Label>
          <NativeSelect id="campaign-list" value={state.leadListId ?? ""} onChange={(e) => set({ leadListId: e.target.value || null })}>
            <option value="">No list chosen</option>
            {(lists.data ?? []).map((l) => <option key={l.id} value={l.id}>{`${l.name} (${l.leadCount})`}</option>)}
          </NativeSelect>
        </div>
        <Button onClick={() => setAdding(true)}>Add leads</Button>
        <Button asChild variant="outline"><Link to="/leads?tab=lists">Manage lists</Link></Button>
      </div>
      {!chosen && (
        <div className="rounded-lg border border-border p-4 text-sm text-muted-foreground">
          <p className="font-medium text-foreground">Add leads to begin</p>
          <p>Import from a CSV, a LinkedIn search, or your saved lists. You can carry on without them, but the campaign cannot launch until it has at least one lead.</p>
        </div>
      )}
      {chosen && <p role="status" className="rounded-lg bg-primary-soft px-3 py-2 text-sm text-primary-soft-foreground">{chosen.name}: {chosen.leadCount} {chosen.leadCount === 1 ? "lead" : "leads"}.</p>}
      <AddLeadsDialog open={adding} onOpenChange={(open) => { setAdding(open); if (!open) void lists.refetch(); }} />
    </section>
  );
}
