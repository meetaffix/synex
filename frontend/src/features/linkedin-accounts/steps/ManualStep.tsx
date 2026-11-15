import { Button } from "@/components/ui/button";
import { StepHeading } from "./StepHeading";

interface Props {
  onRetry: () => void;
  onClose?: () => void;
}

export function ManualStep({ onRetry, onClose }: Props) {
  return (
    <div className="grid gap-4">
      <StepHeading>LinkedIn needs you to verify this sign-in</StepHeading>
      <p className="text-sm text-muted-foreground">
        LinkedIn asked for a security check. Synex will not complete it for you. Sign in to LinkedIn yourself in a
        normal browser and finish the check there. Then come back and connect the account again.
      </p>
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        {onClose && (
          <Button type="button" variant="outline" onClick={onClose}>
            Close
          </Button>
        )}
        <Button type="button" variant="outline" asChild>
          <a href="https://www.linkedin.com/login" target="_blank" rel="noopener noreferrer">
            Open LinkedIn
          </a>
        </Button>
        <Button type="button" onClick={onRetry}>
          Connect again
        </Button>
      </div>
    </div>
  );
}
