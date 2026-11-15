import { UserAvatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ComingNext } from "@/components/shared/ComingNext";
import { requestFailureMessage } from "@/features/linkedin-accounts/copy";
import { cn } from "@/lib/utils";
import { formatDate } from "@/utils/format";
import { useThread } from "./hooks";
import type { Conversation } from "./service";

interface Props {
  conversation: Conversation;
  onBack: () => void;
}

export function ThreadView({ conversation, onBack }: Props) {
  const thread = useThread(conversation.id);
  return (
    <div className="flex h-full min-h-[24rem] min-w-0 flex-col">
      <header className="flex items-start gap-3 border-b border-border p-4">
        <Button variant="ghost" size="sm" className="lg:hidden" onClick={onBack}>
          Back
        </Button>
        <UserAvatar name={conversation.leadName} className="size-10" />
        <div className="min-w-0">
          <h2 className="truncate text-base font-semibold">{conversation.leadName}</h2>
          <p className="truncate text-sm text-muted-foreground">
            {[conversation.leadTitle, conversation.leadCompany].filter(Boolean).join(" at ") || "No title"}
            {conversation.campaignName ? ` · Campaign: ${conversation.campaignName}` : ""}
          </p>
        </div>
      </header>
      <div className="flex-1 overflow-y-auto p-4" aria-live="polite">
        {thread.isLoading && (
          <div role="status" aria-label="Loading messages" className="grid gap-3">
            <Skeleton className="h-12 w-2/3" />
            <Skeleton className="ml-auto h-12 w-2/3" />
          </div>
        )}
        {thread.isError && (
          <div role="alert" className="grid justify-items-start gap-2">
            <p className="text-sm text-danger">Messages could not be loaded. {requestFailureMessage(thread.error)}</p>
            <Button size="sm" variant="outline" onClick={() => void thread.refetch()}>
              Try again
            </Button>
          </div>
        )}
        {thread.data?.length === 0 && <p className="text-sm text-muted-foreground">There are no messages in this conversation yet.</p>}
        <ol className="grid grid-cols-[minmax(0,1fr)] gap-4">
          {thread.data?.map((message) => (
            <li key={message.id} className={message.direction === "outbound" ? "max-w-full justify-self-end text-right" : "max-w-full justify-self-start"}>
              <p className="text-xs text-muted-foreground">
                {message.direction === "outbound" ? "You" : conversation.leadName} · <span className="tabular-nums">{formatDate(message.sentAt, "MMM d, h:mm a")}</span>
                {message.deliveryStatus && message.deliveryStatus !== "sent" ? ` · ${message.deliveryStatus === "queued" ? "Queued" : "Not delivered"}` : ""}
              </p>
              <p className={cn("mt-1 max-w-prose whitespace-pre-wrap break-words rounded-md px-3 py-2 text-left text-sm", message.direction === "outbound" ? "bg-primary-soft text-primary-soft-foreground" : "border border-border bg-surface")}>{message.body}</p>
            </li>
          ))}
        </ol>
      </div>
      <form className="grid gap-2 border-t border-border p-4" onSubmit={(event) => event.preventDefault()}>
        <label htmlFor="reply" className="text-sm font-medium">
          Reply
        </label>
        <Textarea id="reply" rows={3} disabled placeholder="Replies are coming next" />
        <div className="flex justify-end">
          <ComingNext label="Sending replies from the inbox comes next">
            <Button type="submit" disabled>
              Send reply
            </Button>
          </ComingNext>
        </div>
      </form>
    </div>
  );
}
