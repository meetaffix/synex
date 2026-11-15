import { Button } from "@/components/ui/button";
import { UserAvatar } from "@/components/ui/avatar";
import { Skeleton } from "@/components/ui/skeleton";
import { Reveal } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { formatSmartTime } from "@/utils/format";
import type { Conversation } from "./service";

interface Props {
  conversations: Conversation[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function ConversationList({ conversations, selectedId, onSelect }: Props) {
  return (
    <ul aria-label="Conversations" className="divide-y divide-border">
      {conversations.map((conversation, index) => (
        <Reveal as="li" key={conversation.id} index={index}>
          <button
            type="button"
            onClick={() => onSelect(conversation.id)}
            aria-current={conversation.id === selectedId ? "true" : undefined}
            className={cn(
              "flex w-full items-start gap-3 px-4 py-3 text-left transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
              conversation.id === selectedId ? "bg-primary-soft" : "hover:bg-surface-muted/60",
            )}
          >
            <UserAvatar name={conversation.leadName} className="mt-0.5 size-10" />
            <span className="grid min-w-0 flex-1 gap-0.5">
              <span className="flex items-baseline justify-between gap-3">
                <span className="flex min-w-0 items-center gap-2">
                  <span className={cn("truncate text-sm", conversation.unread ? "font-semibold" : "font-medium")}>{conversation.leadName}</span>
                  {conversation.unread && (
                    <>
                      <span aria-hidden className="size-2 shrink-0 rounded-full bg-accent" />
                      <span className="sr-only">Unread</span>
                    </>
                  )}
                </span>
                <span className="shrink-0 text-xs text-muted-foreground">{formatSmartTime(conversation.lastMessageAt)}</span>
              </span>
              <span className="truncate text-xs text-muted-foreground">
                {[conversation.leadTitle, conversation.leadCompany].filter(Boolean).join(" at ") || "No title"}
              </span>
              <span className="truncate text-sm text-muted-foreground">{conversation.lastMessagePreview || "No messages yet"}</span>
            </span>
          </button>
        </Reveal>
      ))}
    </ul>
  );
}

export function ConversationListLoading() {
  return (
    <div role="status" aria-label="Loading conversations" className="grid gap-4 p-4">
      {[0, 1, 2, 3].map((row) => (
        <div key={row} className="flex items-center gap-3">
          <Skeleton className="size-10 shrink-0 rounded-full" />
          <div className="grid flex-1 gap-2">
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-3 w-full" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function ListMessage({ title, children, action }: { title: string; children: string; action?: { label: string; onClick: () => void } }) {
  return (
    <div className="grid justify-items-start gap-2 p-4">
      <p className="text-sm font-medium">{title}</p>
      <p className="text-sm text-muted-foreground">{children}</p>
      {action && (
        <Button size="sm" variant="secondary" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
    </div>
  );
}
