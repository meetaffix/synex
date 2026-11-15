import { Button } from "@/components/ui/button";
import { StepHeading } from "./StepHeading";

interface Props {
  message: string;
  onRetry: () => void;
  onCancel: () => void;
}

/** Polling failed, but the attempt may still be running on the server. */
export function LostStep({ message, onRetry, onCancel }: Props) {
  return (
    <div className="grid gap-4">
      <StepHeading>Synex lost contact with the server</StepHeading>
      <p className="text-sm text-muted-foreground">
        {message} The sign-in may still be running. Check again, or cancel it.
      </p>
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="button" onClick={onRetry}>
          Check again
        </Button>
      </div>
    </div>
  );
}
