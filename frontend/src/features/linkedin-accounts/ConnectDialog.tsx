import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { requestFailureMessage } from "./copy";
import { ConnectFlow } from "./ConnectFlow";
import { useAccountActions } from "./hooks";
import { ReconnectLinkDialog, type LinkState } from "./ReconnectLinkDialog";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Set when reconnecting a known account, so the person signs in with the same LinkedIn email. */
  reconnecting?: string;
}

/** Closing the dialog unmounts the flow, which cancels any attempt still running. */
export function ConnectDialog({ open, onOpenChange, reconnecting }: Props) {
  const actions = useAccountActions();
  const [link, setLink] = useState<LinkState | null>(null);
  const makeLink = () => {
    setLink({ kind: "loading" });
    actions.inviteLink.mutate(undefined, {
      onSuccess: (created) => setLink({ kind: "ready", link: created }),
      onError: (error) => setLink({ kind: "error", message: requestFailureMessage(error) }),
    });
  };
  if (link) return <ReconnectLinkDialog accountName="the new sender" state={link} onRetry={makeLink} onClose={() => { setLink(null); onOpenChange(false); }} />;
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
        {!reconnecting && (
          <section aria-label="Other ways to connect" className="grid gap-2 border-t border-border pt-4 text-sm">
            <h3 className="font-medium">Other ways to connect</h3>
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" variant="outline" disabled aria-describedby="ext-soon">Connect with the Chrome extension</Button>
              <span id="ext-soon" className="text-xs text-muted-foreground">Coming soon. Nothing to install today.</span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" variant="outline" loading={actions.inviteLink.isPending} onClick={makeLink}>Share a connection link</Button>
              <span className="text-xs text-muted-foreground">For when the LinkedIn owner is someone else.</span>
            </div>
          </section>
        )}
      </DialogContent>
    </Dialog>
  );
}
