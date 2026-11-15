import { useId, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { complianceNote, identifierHelp } from "../copy";
import { ProxyInput } from "../ProxyInput";
import { SyncModeFields } from "../SyncModeFields";
import type { SyncMode } from "../schemas";
import type { Credentials } from "../service";

export interface CredentialDefaults {
  identifier: string;
  timezone: string;
  proxyUrl: string;
  syncMode: SyncMode;
}

const TIME_ZONES = Intl.supportedValuesOf("timeZone");
/** The visitor's own time zone, so nobody has to find it in the list (empty when the browser's name is not listed). */
const BROWSER_ZONE = (() => {
  try {
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    return TIME_ZONES.includes(zone) ? zone : "";
  } catch {
    return "";
  }
})();
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PHONE_PATTERN = /^\+[1-9]\d{6,14}$/;

const isEmailOrPhone = (value: string) => {
  const text = value.trim();
  return text.includes("@") ? EMAIL_PATTERN.test(text) : PHONE_PATTERN.test(text.replace(/[\s().-]/g, ""));
};

const schema = z.object({
  identifier: z.string().trim().refine(isEmailOrPhone, identifierHelp),
  password: z.string().min(1, "Enter your LinkedIn password."),
  timezone: z.string().trim(),
  proxyUrl: z.string(),
  syncMode: z.enum(["all", "synex_only"]),
});
type FormValues = z.infer<typeof schema>;

interface Props {
  defaults: CredentialDefaults;
  /** The public reconnect page signs in with email or phone and password only. */
  withOptions: boolean;
  notice?: string;
  onSubmit: (credentials: Credentials, kept: CredentialDefaults) => void;
  onCancel?: () => void;
}

export function CredentialsStep({ defaults, withOptions, notice, onSubmit, onCancel }: Props) {
  const id = useId();
  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { ...defaults, timezone: defaults.timezone || BROWSER_ZONE, password: "" } });

  const submit = (values: FormValues) => {
    const credentials: Credentials = { identifier: values.identifier, password: values.password };
    if (withOptions) {
      credentials.timezone = values.timezone || undefined;
      credentials.proxyUrl = values.proxyUrl || undefined;
      credentials.syncMode = values.syncMode;
    }
    // The password leaves form state as soon as the attempt starts.
    setValue("password", "");
    onSubmit(credentials, {
      identifier: values.identifier,
      timezone: values.timezone,
      proxyUrl: values.proxyUrl,
      syncMode: values.syncMode,
    });
  };

  return (
    <form onSubmit={handleSubmit(submit)} className="grid gap-4" noValidate>
      {notice && (
        <p role="alert" className="rounded-sm border border-danger/30 bg-danger-soft p-3 text-sm text-danger">
          {notice}
        </p>
      )}
      <div className="grid gap-2">
        <Label htmlFor={`${id}-identifier`}>Email or phone</Label>
        <Input
          id={`${id}-identifier`}
          type="text"
          autoComplete="username"
          autoFocus
          aria-invalid={!!errors.identifier}
          aria-describedby={errors.identifier ? `${id}-identifier-error` : `${id}-identifier-help`}
          {...register("identifier")}
        />
        {errors.identifier ? (
          <FieldError id={`${id}-identifier-error`}>{errors.identifier.message}</FieldError>
        ) : (
          <p id={`${id}-identifier-help`} className="text-xs text-muted-foreground">
            The email or phone number you use to sign in to LinkedIn.
          </p>
        )}
      </div>
      <div className="grid gap-2">
        <Label htmlFor={`${id}-password`}>LinkedIn password</Label>
        <Input
          id={`${id}-password`}
          type="password"
          autoComplete="current-password"
          aria-invalid={!!errors.password}
          aria-describedby={`${id}-password-help${errors.password ? ` ${id}-password-error` : ""}`}
          {...register("password")}
        />
        <p id={`${id}-password-help`} className="text-xs text-muted-foreground">
          Synex uses your password once to sign in. It is never saved.
        </p>
        {errors.password && <FieldError id={`${id}-password-error`}>{errors.password.message}</FieldError>}
      </div>
      {withOptions && (
        <>
          <div className="grid gap-2">
            <Label htmlFor={`${id}-timezone`}>Time zone</Label>
            <Input
              id={`${id}-timezone`}
              list={`${id}-zones`}
              autoComplete="off"
              aria-describedby={`${id}-timezone-help`}
              {...register("timezone")}
            />
            <datalist id={`${id}-zones`}>
              {TIME_ZONES.map((zone) => (
                <option key={zone} value={zone} />
              ))}
            </datalist>
            <p id={`${id}-timezone-help`} className="text-xs text-muted-foreground">
              Used for this account's browser and daily limits. It cannot be changed later.
            </p>
          </div>
          <Disclosure title="Sync preferences">
            <SyncModeFields value={watch("syncMode")} onChange={(mode) => setValue("syncMode", mode)} />
          </Disclosure>
          <Disclosure title="Advanced: proxy">
            <ProxyInput value={watch("proxyUrl")} onChange={(url) => setValue("proxyUrl", url)} />
          </Disclosure>
        </>
      )}
      <p className="text-xs text-muted-foreground">{complianceNote}</p>
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
        )}
        <Button type="submit">Connect LinkedIn account</Button>
      </div>
    </form>
  );
}

function Disclosure({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details>
      <summary className="w-fit cursor-pointer rounded-sm text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        {title}
      </summary>
      <div className="mt-4">{children}</div>
    </details>
  );
}

function FieldError({ id, children }: { id: string; children: ReactNode }) {
  return (
    <p id={id} role="alert" className="text-xs text-danger">
      {children}
    </p>
  );
}
