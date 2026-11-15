import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ConnectFlow } from "./ConnectFlow";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Set when reconnecting a known account, so the person signs in with the same LinkedIn email. */
  reconnecting?: string;
}

/** Closing the dialog unmounts the flow, which cancels any attempt still running. */
export function ConnectDialog({ open, onOpenChange, reconnecting }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader className="space-y-2">
          <DialogTitle className="text-xl">
            {reconnecting ? `Reconnect ${reconnecting}` : "Connect LinkedIn account"}
          </DialogTitle>
          <DialogDescription>
            {reconnecting
              ? "Sign in with the same LinkedIn email this account was connected with."
              : "Sign in to the LinkedIn account you want Synex to send from."}
          </DialogDescription>
        </DialogHeader>
        <ConnectFlow scope={{ kind: "account" }} onClose={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}
