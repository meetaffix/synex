import { useId } from "react";
import { Radio } from "@/components/ui/radio";
import type { SyncMode } from "./schemas";

const OPTIONS: { value: SyncMode; label: string; help: string }[] = [
  {
    value: "synex_only",
    label: "Only conversations from Synex campaigns",
    help: "Synex imports only conversations with people your campaigns contacted. Recommended.",
  },
  {
    value: "all",
    label: "All LinkedIn conversations",
    help: "Synex imports every conversation on this account, including ones that did not start in Synex.",
  },
];

interface Props {
  value: SyncMode;
  onChange: (value: SyncMode) => void;
  /** Only the person who connected the account can change it. */
  disabled?: boolean;
}

export function SyncModeFields({ value, onChange, disabled = false }: Props) {
  const id = useId();
  return (
    <fieldset className="grid gap-4" disabled={disabled}>
      <legend className="sr-only">Conversation sync</legend>
      {OPTIONS.map((option) => (
        <div key={option.value} className="flex items-start gap-3">
          <Radio
            id={`${id}-${option.value}`}
            name={`${id}-sync`}
            checked={value === option.value}
            onChange={() => onChange(option.value)}
            aria-describedby={`${id}-${option.value}-help`}
          />
          <div className="grid gap-1">
            <label htmlFor={`${id}-${option.value}`} className="text-sm font-medium">
              {option.label}
            </label>
            <p id={`${id}-${option.value}-help`} className="text-xs text-muted-foreground">
              {option.help}
            </p>
          </div>
        </div>
      ))}
      <p className="text-xs text-muted-foreground">
        {disabled
          ? "Only the person who connected this account can change this."
          : "Only the person who connects an account can change this later."}
      </p>
    </fieldset>
  );
}
