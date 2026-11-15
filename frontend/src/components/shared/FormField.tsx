import { cloneElement, isValidElement, useId, type ReactElement, type ReactNode } from "react";
import { Label } from "@/components/ui/label";

interface Props {
  label: string;
  /** The field itself (Input, Textarea, NativeSelect). It is given the id and the described-by link. */
  children: ReactElement<{ id?: string; "aria-invalid"?: boolean; "aria-describedby"?: string }>;
  /** Shown under the field; replaced by the error when there is one. */
  help?: ReactNode;
  error?: string;
  optional?: boolean;
  /** Something on the label's line, such as a "Forgot password?" link. */
  aside?: ReactNode;
}

/** Label above, field, then help or error below, wired together for assistive technology. */
export function FormField({ label, children, help, error, optional, aside }: Props) {
  const id = useId();
  const messageId = `${id}-message`;
  const message = error ?? help;
  const field = isValidElement(children)
    ? cloneElement(children, { id, "aria-invalid": error ? true : undefined, "aria-describedby": message ? messageId : undefined })
    : children;
  return (
    <div className="grid gap-2">
      <div className="flex items-center justify-between gap-3">
        <Label htmlFor={id}>
          {label}
          {optional && <span className="font-normal text-muted-foreground"> (optional)</span>}
        </Label>
        {aside}
      </div>
      {field}
      {message && (
        <p id={messageId} className={error ? "text-xs text-danger" : "text-xs text-muted-foreground"}>
          {message}
        </p>
      )}
    </div>
  );
}
