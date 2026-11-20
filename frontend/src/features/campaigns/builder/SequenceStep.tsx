import { SmartGraph } from "./SmartGraph";
import type { BuilderState } from "./model";

interface Props {
  state: BuilderState;
  set: (change: Partial<BuilderState>) => void;
  campaignId: string;
  audienceConnections?: boolean;
}

/** Step 3, the one sequence designer: a map that starts empty. Every action, including the connection request, is added from the plus button. */
export function SequenceStep({ state, set, campaignId, audienceConnections }: Props) {
  return (
    <section aria-labelledby="seq-h" className="grid grid-cols-1 gap-4">
      <div>
        <h2 id="seq-h" className="text-lg font-semibold">Sequence</h2>
        <p className="text-sm text-muted-foreground">Press Add action to build the sequence, and split it with If steps. Each branch ends when it runs out of steps. Click any step to change its settings.</p>
      </div>
      <SmartGraph state={state} set={set} campaignId={campaignId} audienceConnections={audienceConnections} />
    </section>
  );
}
