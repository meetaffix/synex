import { Illustration } from "@/components/brand/Illustration";
import { Button } from "@/components/ui/button";
import { useSenderAccounts } from "../hooks";
import { StepHeading } from "./StepHeading";

interface Props {
  /** Set on the signed-in flow; the public reconnect page has no account list. */
  accountId?: string;
  onClose?: () => void;
}

/** A short, quiet celebration: the check draws itself once, and the next step is right there. */
export function SucceededStep({ accountId, onClose }: Props) {
  return (
    <div className="grid justify-items-center gap-4 text-center">
      <Illustration name="success" className="h-32 animate-pop" />
      <StepHeading>{accountId ? "Account connected" : "Account reconnected"}</StepHeading>
      {accountId ? (
        <ConnectedMessage accountId={accountId} />
      ) : (
        <p className="text-sm text-muted-foreground">The account is signed in again. You can close this page. The link cannot be used a second time.</p>
      )}
      {onClose && (
        <Button type="button" onClick={onClose}>
          Done
        </Button>
      )}
    </div>
  );
}

function ConnectedMessage({ accountId }: { accountId: string }) {
  const accounts = useSenderAccounts();
  const name = accounts.data?.find((account) => account.id === accountId)?.name;
  return (
    <p className="text-sm text-muted-foreground">
      {name ?? "The account"} is connected. Next, check its daily limit; lower limits are safer. Then import leads to start a campaign.
    </p>
  );
}
