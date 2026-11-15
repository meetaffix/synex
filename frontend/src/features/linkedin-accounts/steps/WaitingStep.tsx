import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StepHeading } from "./StepHeading";

interface Props {
  title: string;
  children: string;
  onCancel: () => void;
}

/** Shared by the "starting" and "approve in the app" states. */
export function WaitingStep({ title, children, onCancel }: Props) {
  return (
    <div className="grid gap-4">
      <div className="flex items-center gap-3">
        <Loader2 className="size-5 shrink-0 animate-spin text-muted-foreground motion-reduce:animate-none" aria-hidden />
        <StepHeading>{title}</StepHeading>
      </div>
      <p className="text-sm text-muted-foreground">{children}</p>
      <div className="flex justify-end">
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
