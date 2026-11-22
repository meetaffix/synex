import { Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { UserAvatar } from "@/components/ui/avatar";
import { Skeleton } from "@/components/ui/skeleton";
import { Reveal } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { formatSmartTime } from "@/utils/format";
import { INTEREST_LABEL, type InboxItem } from "./model";

interface Props {
  conversations: InboxItem[];
  selectedId: string | null;
  checked: Set<string>;
  onSelect: (id: string) => void;
  onCheck: (id: string, on: boolean) => void;
  onStar: (item: InboxItem) => void;
}

export function ConversationList({ conversations, selectedId, checked, onSelect, onCheck, onStar }: Props) {
  return (
    <ul aria-label="Conversations" className="divide-y divide-border">
      {conversations.map((c, index) => (
        <Reveal as="li" key={c.id} index={index} className={cn("flex items-start gap-1 border-l-[3px] pl-2 transition-colors", c.id === selectedId ? "border-l-primary bg-primary-soft" : c.unread ? "border-l-accent hover:bg-surface-muted/60" : "border-l-transparent hover:bg-surface-muted/60")}>
          <span className="pt-4"><Checkbox aria-label={`Select ${c.leadName}`} checked={checked.has(c.id)} onCheckedChange={(v) => onCheck(c.id, v === true)} /></span>
          <button type="button" onClick={() => onSelect(c.id)} aria-current={c.id === selectedId ? "true" : undefined}
            className="flex min-w-0 flex-1 items-start gap-3 px-2 py-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring">
            <UserAvatar name={c.leadName} src={c.avatarUrl ?? undefined} className="mt-0.5 size-10 ring-2 ring-surface" />
            <span className="grid min-w-0 flex-1 gap-0.5">
              <span className="flex items-baseline justify-between gap-3">
                <span className="flex min-w-0 items-center gap-2">
                  <span className={cn("truncate text-sm", c.unread ? "font-semibold" : "font-medium")}>{c.leadName}</span>
                  {c.unread && (<><span aria-hidden className="size-2 shrink-0 rounded-full bg-accent" /><span className="sr-only">Unread</span></>)}
                </span>
                {c.lastMessageAt && <span className="shrink-0 text-xs text-muted-foreground">{formatSmartTime(c.lastMessageAt)}</span>}
              </span>
              {[c.leadTitle, c.leadCompany].some(Boolean) && <span className="truncate text-xs text-muted-foreground">{[c.leadTitle, c.leadCompany].filter(Boolean).join(" at ")}</span>}
              <span className={cn("truncate text-sm", c.unread ? "text-foreground" : "text-muted-foreground")}>{c.hasDraft ? "Draft: " : ""}{c.lastMessagePreview || "No messages yet"}</span>
              <span className="flex flex-wrap items-center gap-1.5 pt-1 text-xs">
                {c.accountName && <span className="rounded-full bg-surface-muted px-2 py-0.5">Received by {c.accountName}</span>}
                {c.needsReply && <span className="rounded-full bg-warning-soft px-2 py-0.5 text-warning">Needs reply</span>}
                {c.interest && <span className="rounded-full bg-primary-soft px-2 py-0.5 text-primary-soft-foreground">{INTEREST_LABEL[c.interest] ?? c.interest}</span>}
                {c.scheduledCount > 0 && <span className="rounded-full bg-surface-muted px-2 py-0.5">Scheduled</span>}
                {c.tags.map((t) => <span key={t} className="rounded-full border border-border px-2 py-0.5">{t}</span>)}
              </span>
            </span>
          </button>
          <Button type="button" size="icon-sm" variant="ghost" className="mt-2" aria-pressed={c.starred} aria-label={c.starred ? `Unstar ${c.leadName}` : `Star ${c.leadName}`} onClick={() => onStar(c)}>
            <Star className={c.starred ? "fill-current text-warning" : ""} />
          </Button>
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
          <div className="grid flex-1 gap-2"><Skeleton className="h-4 w-1/3" /><Skeleton className="h-3 w-2/3" /></div>
        </div>
      ))}
    </div>
  );
}

export function ListMessage({ title, children, action }: { title: string; children: React.ReactNode; action?: { label: string; onClick: () => void } }) {
  return (
    <div className="grid justify-items-center gap-2 p-6 text-center">
      <p className="text-sm font-medium">{title}</p>
      <p className="text-sm text-muted-foreground">{children}</p>
      {action && <Button size="sm" variant="outline" onClick={action.onClick}>{action.label}</Button>}
    </div>
  );
}
