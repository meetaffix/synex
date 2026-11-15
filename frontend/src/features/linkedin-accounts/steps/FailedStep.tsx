import { Button } from "@/components/ui/button";
import { failureCopy } from "../copy";
import type { AttemptErrorCode } from "../schemas";
import { StepHeading } from "./StepHeading";

interface Props {
  code: AttemptErrorCode;
  message: string;
  onRetry: () => void;
  onClose?: () => void;
}

export function FailedStep({ code, message, onRetry, onClose }: Props) {
  const copy = failureCopy[code];
  return (
    <div className="grid gap-4">
      <StepHeading>{copy.title}</StepHeading>
      <p className="text-sm text-muted-foreground">{copy.detail}</p>
      {message !== copy.detail && <p className="text-xs text-muted-foreground">{message}</p>}
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        {onClose && (
          <Button type="button" variant="outline" onClick={onClose}>
            Close
          </Button>
        )}
        <Button type="button" onClick={onRetry}>
          Try again
        </Button>
      </div>
    </div>
  );
}
