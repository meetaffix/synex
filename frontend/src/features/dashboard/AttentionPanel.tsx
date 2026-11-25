import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useCleared } from "./WorkPanels";
import { AlertTriangle, ChevronRight, MessageSquare, PauseCircle, type LucideIcon } from "lucide-react";
import { Illustration } from "@/components/brand/Illustration";
import { UserAvatar } from "@/components/ui/avatar";
import type { Campaign } from "@/features/campaigns/service";
import type { Conversation } from "@/features/inbox/service";
import type { SenderAccount } from "@/features/linkedin-accounts/schemas";
import { Reveal } from "@/lib/motion";

interface Row {
  id: string;
  to: string;
  icon: LucideIcon;
  tone: string;
  title: string;
  detail: string;
}

const ACCOUNT_PROBLEMS: Partial<Record<SenderAccount["status"], string>> = {
  needs_reconnect: "needs to be reconnected",
  restricted: "is restricted by LinkedIn",
  disconnected: "is disconnected",
  paused: "is paused",
};

/** What needs a person right now, each one click away. Built only from data Synex already has. */
export function AttentionPanel({ conversations, accounts, campaigns }: { conversations: Conversation[]; accounts: SenderAccount[]; campaigns: Campaign[] }) {
  const unread = conversations.filter((conversation) => conversation.unread);
  const rows: Row[] = [];
  if (unread.length > 0) {
    rows.push({
      id: "replies",
      to: "/inbox",
      icon: MessageSquare,
      tone: "bg-accent-soft text-accent",
      title: `${unread.length} ${unread.length === 1 ? "reply" : "replies"} waiting`,
      detail: `Latest from ${unread[0].leadName}`,
    });
  }
  for (const account of accounts) {
    const problem = ACCOUNT_PROBLEMS[account.status];
    if (problem) {
      rows.push({
        id: `account-${account.id}`,
        to: "/linkedin-accounts",
        icon: AlertTriangle,
        tone: "bg-warning-soft text-warning",
        title: `${account.name} ${problem}`,
        detail: account.pausedReason ?? "Open Sender accounts to fix it.",
      });
    }
  }
  for (const campaign of campaigns.filter((c) => c.status === "paused")) {
    rows.push({ id: `campaign-${campaign.id}`, to: "/campaigns", icon: PauseCircle, tone: "bg-info-soft text-info", title: `${campaign.name} is paused`, detail: "It sends nothing until it is resumed." });
  }

  return (
    <section aria-labelledby="attention-title" className="grid min-w-0 grid-cols-[minmax(0,1fr)] content-start gap-3 rounded-lg border border-border bg-surface p-4 shadow-raised sm:p-6">
      <h2 id="attention-title" className="text-base font-semibold">
        Needs your attention
      </h2>
      {rows.length === 0 ? (
        <div className="grid justify-items-center gap-2 py-4 text-center">
          <Illustration name="success" className="h-20" />
          <p className="text-sm font-medium">Nothing needs you right now</p>
          <p className="text-sm text-muted-foreground">New replies and account problems appear here.</p>
        </div>
      ) : (
        <ul className="grid gap-1">
          {rows.map((row, index) => (
            <Reveal as="li" key={row.id} index={index} className="min-w-0">
              <Link to={row.to} className="group flex min-h-14 items-center gap-3 rounded-md p-2 transition-colors duration-150 hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                <span aria-hidden className={`grid size-9 shrink-0 place-items-center rounded-full ${row.tone}`}>
                  <row.icon className="size-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{row.title}</span>
                  <span className="block truncate text-xs text-muted-foreground">{row.detail}</span>
                </span>
                <ChevronRight className="size-4 shrink-0 text-muted-foreground transition-transform duration-150 group-hover:translate-x-0.5" aria-hidden />
              </Link>
            </Reveal>
          ))}
        </ul>
      )}
    </section>
  );
}

function ago(value: string): string {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 60_000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

/** The latest conversations, with the people in them. */
export function ActivityFeed({ conversations }: { conversations: Conversation[] }) {
  const cleared = useCleared("activity");
  const recent = [...conversations].filter((c) => cleared.isNew(c.lastMessageAt)).sort((a, b) => b.lastMessageAt.localeCompare(a.lastMessageAt)).slice(0, 5);
  return (
    <section aria-labelledby="activity-title" className="grid min-w-0 self-start grid-cols-[minmax(0,1fr)] content-start gap-3 rounded-lg border border-border bg-surface p-4 shadow-raised sm:p-6">
      <div className="flex items-center justify-between gap-3">
        <h2 id="activity-title" className="text-base font-semibold">
          Recent activity
        </h2>
        <span className="flex items-center gap-1">
          {recent.length > 0 ? (
            <Button size="sm" variant="ghost" onClick={cleared.clear}>Clear</Button>
          ) : cleared.clearedAt && conversations.length > 0 ? (
            <Button size="sm" variant="ghost" onClick={cleared.showAll}>Show all</Button>
          ) : null}
          <Link to="/inbox" className="rounded-sm text-sm font-medium text-primary-ink underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            Open inbox
          </Link>
        </span>
      </div>
      {recent.length === 0 ? (
        <p className="text-sm text-muted-foreground">{cleared.clearedAt ? "Nothing new since you cleared it" : "Replies from your campaigns appear here as they arrive"}</p>
      ) : (
        <ul className="grid gap-1">
          {recent.map((conversation, index) => (
            <Reveal as="li" key={conversation.id} index={index} className="min-w-0">
              <Link to="/inbox" className="flex min-h-14 items-center gap-3 rounded-md p-2 transition-colors duration-150 hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                <UserAvatar name={conversation.leadName} className="size-9" />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium">{conversation.leadName}</span>
                    {conversation.unread && (
                      <>
                        <span aria-hidden className="size-2 shrink-0 rounded-full bg-accent" />
                        <span className="sr-only">Unread</span>
                      </>
                    )}
                  </span>
                  <span className="block truncate text-xs text-muted-foreground">{conversation.lastMessagePreview ?? "No messages yet"}</span>
                </span>
                <span className="shrink-0 text-xs text-muted-foreground">{ago(conversation.lastMessageAt)}</span>
              </Link>
            </Reveal>
          ))}
        </ul>
      )}
    </section>
  );
}
