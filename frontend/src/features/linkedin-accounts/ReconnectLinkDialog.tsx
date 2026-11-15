import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate } from "@/utils/format";
import type { ReconnectLink } from "./schemas";

export type LinkState = { kind: "loading" } | { kind: "ready"; link: ReconnectLink } | { kind: "error"; message: string };

interface Props {
  accountName: string;
  state: LinkState;
  onRetry: () => void;
  onClose: () => void;
}

export function ReconnectLinkDialog({ accountName, state, onRetry, onClose }: Props) {
  const id = useId();
  const [copied, setCopied] = useState(false);

  const copy = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      (document.getElementById(id) as HTMLInputElement | null)?.select();
    }
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader className="space-y-2">
          <DialogTitle>Reconnect link for {accountName}</DialogTitle>
          <DialogDescription>
            {state.kind === "ready"
              ? `Send this to the person who owns the LinkedIn account. They sign in on a Synex page without needing a Synex login. The link works once and expires on ${formatDate(state.link.expiresAt, "PPp")}.`
              : "Send this to the person who owns the LinkedIn account. They sign in on a Synex page without needing a Synex login."}
          </DialogDescription>
        </DialogHeader>
        {state.kind === "loading" && (
          <div role="status" aria-label="Creating the reconnect link" className="grid gap-2">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-9 w-full" />
            <p className="text-sm text-muted-foreground">Creating the link…</p>
          </div>
        )}
        {state.kind === "error" && (
          <p role="alert" className="text-sm text-danger">
            The link could not be created. {state.message}
          </p>
        )}
        {state.kind === "ready" && (
          <div className="grid gap-2">
            <Label htmlFor={id}>Reconnect link</Label>
            <Input id={id} readOnly value={state.link.url} onFocus={(event) => event.target.select()} />
          </div>
        )}
        <p role="status" aria-live="polite" className="min-h-4 text-xs text-muted-foreground">
          {copied ? "Link copied." : ""}
        </p>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
          {state.kind === "ready" && <Button onClick={() => void copy(state.link.url)}>Copy link</Button>}
          {state.kind === "error" && <Button onClick={onRetry}>Try again</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
