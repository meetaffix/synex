import { useState } from "react";
import { useConnectFlow, type FlowView } from "./hooks";
import type { FlowScope } from "./service";
import { CodeStep } from "./steps/CodeStep";
import { CredentialsStep, type CredentialDefaults } from "./steps/CredentialsStep";
import { FailedStep } from "./steps/FailedStep";
import { LostStep } from "./steps/LostStep";
import { ManualStep } from "./steps/ManualStep";
import { SucceededStep } from "./steps/SucceededStep";
import { StartingStep } from "./steps/StartingStep";
import { WaitingStep } from "./steps/WaitingStep";

interface Props {
  scope: FlowScope;
  /** Present when the flow lives in a dialog; the public page has nothing to close. */
  onClose?: () => void;
}

const announcements: Record<FlowView["kind"], string> = {
  form: "Enter your LinkedIn sign-in details.",
  starting: "Signing in to LinkedIn.",
  code: "LinkedIn sent a verification code. Enter it to continue.",
  approval: "Approve the sign-in in your LinkedIn app.",
  manual: "LinkedIn needs you to verify this sign-in yourself.",
  succeeded: "The account is connected.",
  failed: "The connection did not complete.",
  lost: "Synex lost contact with the server.",
};

const browserTimeZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone;

export function ConnectFlow({ scope, onClose }: Props) {
  const flow = useConnectFlow(scope);
  const [kept, setKept] = useState<CredentialDefaults>({
    identifier: "",
    timezone: browserTimeZone(),
    proxyUrl: "",
    syncMode: "synex_only",
  });
  const { view } = flow;

  const cancel = () => {
    flow.cancel();
    if (onClose) onClose();
    else flow.reset();
  };

  return (
    <div>
      <p role="status" aria-live="polite" className="sr-only">
        {announcements[view.kind]}
      </p>
      {view.kind === "form" && (
        <CredentialsStep
          defaults={kept}
          withOptions={scope.kind === "account"}
          notice={view.notice}
          onCancel={onClose}
          onSubmit={(credentials, keep) => {
            setKept(keep);
            void flow.start(credentials);
          }}
        />
      )}
      {view.kind === "starting" && (
        <StartingStep onCancel={cancel} />
      )}
      {view.kind === "code" && (
        <CodeStep challenge={view.challenge} error={view.error} onSubmit={flow.sendCode} onCancel={cancel} />
      )}
      {view.kind === "approval" && (
        <WaitingStep title="Approve the sign-in in your LinkedIn app" onCancel={cancel}>
          Open the LinkedIn app on your phone and approve the sign-in request. This window continues on its own.
        </WaitingStep>
      )}
      {view.kind === "manual" && <ManualStep onRetry={flow.reset} onClose={onClose} />}
      {view.kind === "succeeded" && <SucceededStep accountId={scope.kind === "account" ? view.accountId : undefined} onClose={onClose} onConnectAnother={() => { setKept((k) => ({ ...k, identifier: "" })); flow.reset(); }} />}
      {view.kind === "failed" && <FailedStep code={view.code} message={view.message} onRetry={flow.reset} onClose={onClose} />}
      {view.kind === "lost" && <LostStep message={view.message} onRetry={flow.retryPolling} onCancel={cancel} />}
    </div>
  );
}
