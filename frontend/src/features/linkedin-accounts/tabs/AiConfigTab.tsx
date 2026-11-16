import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Radio } from "@/components/ui/radio";
import { api } from "@/services/client";
import { requestFailureMessage } from "../copy";
import { detailKeys, type AccountDetails } from "../management";

const catalogueSchema = z.object({
  voices: z.array(z.object({ id: z.string(), label: z.string(), gender: z.string(), accent: z.string(), model: z.string(), licence: z.string() })),
  engine: z.object({ name: z.string(), available: z.boolean(), reason: z.string().nullable() }),
  clone: z.object({ available: z.boolean(), reason: z.string() }),
  accents: z.array(z.object({ label: z.string(), available: z.boolean(), reason: z.string().optional() })),
});

function useVoices() {
  return useQuery({ queryKey: ["voice-catalogue"], queryFn: async () => catalogueSchema.parse(await api.get("/linkedin-accounts/voices/catalogue")), staleTime: 10 * 60_000 });
}

/** The voice this sender uses for voice notes. Cloning stays off until a commercially licensed model is installed. */
export function AiConfigTab({ accountId, details }: { accountId: string; details: AccountDetails }) {
  const qc = useQueryClient();
  const catalogue = useVoices();
  const [open, setOpen] = useState(false);
  const [choice, setChoice] = useState<string | null>(details.voiceId);
  const assign = useMutation({
    mutationFn: (voiceId: string | null) => api.put(`/linkedin-accounts/${accountId}/voice`, { voiceId }),
    onSuccess: () => qc.invalidateQueries({ queryKey: detailKeys.one(accountId) }),
  });
  const assigned = catalogue.data?.voices.find((voice) => voice.id === details.voiceId);

  return (
    <div className="grid max-w-2xl gap-8">
      <section className="grid gap-3">
        <h2 className="text-base font-semibold">Voice for voice notes</h2>
        <p className="text-sm text-muted-foreground">
          Voice notes in a campaign are spoken in this sender's voice. Pick one of the preset voices. Every preset uses training data licensed for commercial use.
        </p>
        <p className="text-sm" data-testid="assigned-voice">
          <span className="text-muted-foreground">Assigned voice: </span>
          <span className="font-medium">{assigned ? `${assigned.label} (${assigned.accent}, ${assigned.gender})` : "No voice assigned"}</span>
        </p>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" disabled={!catalogue.data} onClick={() => { setChoice(details.voiceId); setOpen(true); }}>{assigned ? "Change voice" : "Assign voice"}</Button>
          {assigned && (
            <Button size="sm" variant="outline" loading={assign.isPending} onClick={() => assign.mutate(null, { onSuccess: () => toast.success("Voice removed."), onError: (e) => toast.error(requestFailureMessage(e)) })}>
              Remove voice
            </Button>
          )}
        </div>
        {catalogue.isError && <p role="alert" className="text-sm text-danger">{requestFailureMessage(catalogue.error)}</p>}
      </section>

      <section className="grid gap-3">
        <h2 className="text-base font-semibold">Clone my voice</h2>
        <div>
          <Button size="sm" variant="outline" disabled aria-describedby="clone-why">Clone my voice (coming soon)</Button>
        </div>
        <p id="clone-why" className="text-sm text-muted-foreground">{catalogue.data?.clone.reason ?? "Loading."}</p>
      </section>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[90vh] max-w-lg overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Select a voice</DialogTitle>
            <DialogDescription>Choose how this sender sounds in voice notes.</DialogDescription>
          </DialogHeader>
          {catalogue.data && (
            <div className="grid gap-3">
              {!catalogue.data.engine.available && <p role="note" className="rounded-lg border border-border bg-surface-muted p-3 text-xs text-muted-foreground">{catalogue.data.engine.reason}</p>}
              <ul className="grid gap-2" aria-label="Preset voices">
                {catalogue.data.voices.map((voice) => (
                  <li key={voice.id} className="flex items-start gap-3 rounded-lg border border-border p-3">
                    <Radio id={`voice-${voice.id}`} name="voice" checked={choice === voice.id} onChange={() => setChoice(voice.id)} />
                    <div className="grid min-w-0 flex-1 gap-0.5">
                      <label htmlFor={`voice-${voice.id}`} className="text-sm font-medium">{voice.label}</label>
                      <p className="text-xs text-muted-foreground">{voice.accent}, {voice.gender}</p>
                      <p className="text-xs text-muted-foreground">Licence: {voice.licence}</p>
                    </div>
                    <Button size="sm" variant="outline" disabled={!catalogue.data.engine.available} aria-label={`Play a sample of ${voice.label}`}>Sample</Button>
                  </li>
                ))}
              </ul>
              <p className="text-xs text-muted-foreground">
                Accents: {catalogue.data.accents.map((accent) => (accent.available ? accent.label : `${accent.label} (unavailable: ${accent.reason})`)).join("; ")}.
              </p>
            </div>
          )}
          <DialogFooter className="mt-2">
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button disabled={!choice || choice === details.voiceId} loading={assign.isPending}
              onClick={() => assign.mutate(choice, { onSuccess: () => { toast.success("Voice assigned."); setOpen(false); }, onError: (e) => toast.error(requestFailureMessage(e)) })}>
              Select voice
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
