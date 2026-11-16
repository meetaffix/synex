import { Illustration } from "@/components/brand/Illustration";
import { Button } from "@/components/ui/button";
import { useSenderAccounts } from "../hooks";
import { StepHeading } from "./StepHeading";

interface Props {
  /** Set on the signed-in flow; the public reconnect page has no account list. */
  accountId?: string;
  onClose?: () => void;
  /** Starts a new sign-in form in the same panel. */
  onConnectAnother?: () => void;
}

/** A short, quiet celebration: the check draws itself once, and the next step is right there. */
export function SucceededStep({ accountId, onClose, onConnectAnother }: Props) {
  return (
    <div className="grid justify-items-center gap-4 text-center">
      <Illustration name="success" className="h-32 animate-pop" />
      <StepHeading>{accountId ? "Account connected" : "Account reconnected"}</StepHeading>
      {accountId ? (
        <ConnectedMessage accountId={accountId} />
      ) : (
        <p className="text-sm text-muted-foreground">The account is signed in again. You can close this page. The link cannot be used a second time.</p>
      )}
      <div className="flex flex-col-reverse gap-2 sm:flex-row">
        {accountId && onConnectAnother && (
          <Button type="button" variant="outline" onClick={onConnectAnother}>
            Connect another account
          </Button>
        )}
        {onClose && (
          <Button type="button" onClick={onClose}>
            Done
          </Button>
        )}
      </div>
    </div>
  );
}

function ConnectedMessage({ accountId }: { accountId: string }) {
  const accounts = useSenderAccounts();
  const name = accounts.data?.find((account) => account.id === accountId)?.name;
  return (
    <p className="text-sm text-muted-foreground">
      {name ?? "The account"} is connected and stopped: its daily limit is 0 until you set one. Choose a limit on the account (it then ramps up from 5 a day), then import leads to start a campaign.
    </p>
  );
}
