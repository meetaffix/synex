import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { codeCopy } from "../copy";
import type { Attempt } from "../schemas";
import { StepHeading } from "./StepHeading";

interface Props {
  challenge: NonNullable<Attempt["challenge"]>;
  /** A rejected code keeps the attempt at this step with the reason attached. */
  error?: string;
  onSubmit: (code: string) => Promise<void>;
  onCancel: () => void;
}

export function CodeStep({ challenge, error, onSubmit, onCancel }: Props) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [code, setCode] = useState("");
  const [localError, setLocalError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const copy = codeCopy[challenge.type];
  const message = localError ?? error;

  useEffect(() => {
    input.current?.focus();
  }, []);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const value = code.trim();
    if (!/^\d{4,10}$/.test(value)) {
      setLocalError("Enter the code using digits only.");
      input.current?.focus();
      return;
    }
    setLocalError(undefined);
    setBusy(true);
    await onSubmit(value);
    setBusy(false);
    setCode("");
    input.current?.focus();
  };

  return (
    <form onSubmit={submit} className="grid gap-4" noValidate>
      <StepHeading>Enter your verification code</StepHeading>
      <p className="text-sm text-muted-foreground">{copy.prompt}</p>
      {challenge.hint && <p className="text-sm">{challenge.hint}</p>}
      <div className="grid gap-2">
        <Label htmlFor={`${id}-code`}>{copy.label}</Label>
        <Input
          id={`${id}-code`}
          ref={input}
          inputMode="numeric"
          autoComplete="one-time-code"
          value={code}
          onChange={(event) => setCode(event.target.value)}
          aria-invalid={!!message}
          aria-describedby={message ? `${id}-error` : undefined}
          className="tabular-nums"
        />
        {message && (
          <p id={`${id}-error`} role="alert" className="text-xs text-danger">
            {message}
          </p>
        )}
      </div>
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" loading={busy}>
          Verify code
        </Button>
      </div>
    </form>
  );
}
