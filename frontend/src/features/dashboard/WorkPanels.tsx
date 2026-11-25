import { useState } from "react";
import { Link } from "react-router-dom";
import { MessageSquareReply, Play } from "lucide-react";
import { UserAvatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import type { Campaign } from "@/features/campaigns/service";
import { emptyFilter, useInboxList } from "@/features/inbox/model";
import { formatRelative } from "@/utils/format";

/** "Clear" hides what is already handled, on this device. Nothing is deleted; "Show all" brings it back. */
export function useCleared(key: string) {
  const storageKey = `synex.cleared.${key}`;
  const [clearedAt, setClearedAt] = useState<string | null>(() => {
    try {
      return window.localStorage.getItem(storageKey);
    } catch {
      return null;
    }
  });
  const save = (value: string | null) => {
    setClearedAt(value);
    try {
      if (value) window.localStorage.setItem(storageKey, value);
      else window.localStorage.removeItem(storageKey);
    } catch {
      /* private mode: clearing still works for this visit */
    }
  };
  return {
    clearedAt,
    clear: () => save(new Date().toISOString()),
    showAll: () => save(null),
    isNew: (at: string | null | undefined) => !clearedAt || (!!at && at > clearedAt),
  };
}

function PanelHead({ id, title, count, action }: { id: string; title: string; count?: number; action?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <h2 id={id} className="flex items-baseline gap-2 text-base font-semibold">
        {title}
        {count !== undefined && <span className="font-mono text-xs font-normal tabular-nums text-muted-foreground">{count}</span>}
      </h2>
      {action}
    </div>
  );
}

const percent = (part: number, whole: number) => (whole > 0 ? Math.round((part / whole) * 100) : 0);

/** Campaigns that are sending now: how far each has got through its leads, and what came back. */
export function RunningCampaigns({ campaigns }: { campaigns: Campaign[] }) {
  const running = campaigns.filter((c) => c.status === "active");
  return (
    <section aria-labelledby="running-title" className="grid min-w-0 content-start gap-3 rounded-lg border border-border bg-surface p-5 shadow-raised">
      <PanelHead id="running-title" title="Running campaigns" count={running.length}
        action={<Link to="/campaigns" className="text-sm font-medium text-primary-ink underline-offset-4 hover:underline">All campaigns</Link>} />
      {running.length === 0 ? (
        <div className="flex items-center justify-between gap-3 rounded-md bg-surface-muted px-4 py-3">
          <span className="flex items-center gap-2 text-sm text-muted-foreground"><Play className="size-4" aria-hidden /> Nothing is sending right now</span>
          <Button asChild size="sm"><Link to="/campaigns/new">New campaign</Link></Button>
        </div>
      ) : (
        <ul className="grid gap-2">
          {running.map((c) => {
            const reached = percent(c.stats.invitesSent + c.stats.messagesSent > 0 ? Math.max(c.stats.invitesSent, c.stats.connected) : 0, c.stats.totalLeads);
            return (
              <li key={c.id}>
                <Link to={`/campaigns/${c.id}`} className="grid gap-2 rounded-md px-3 py-2.5 transition-colors duration-150 hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                  <span className="flex items-center justify-between gap-3">
                    <span className="flex min-w-0 items-center gap-2">
                      <span aria-hidden className="size-2 shrink-0 rounded-full bg-primary" />
                      <span className="truncate text-sm font-medium">{c.name}</span>
                    </span>
                    <span className="shrink-0 font-mono text-xs tabular-nums text-muted-foreground">{c.stats.replied} replied · {c.stats.connected} accepted</span>
                  </span>
                  <span className="flex items-center gap-3">
                    <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-muted" role="progressbar" aria-label={`${c.name}: ${reached}% of leads reached`} aria-valuenow={reached} aria-valuemin={0} aria-valuemax={100}>
                      <span className="block h-full rounded-full bg-primary" style={{ width: `${reached}%` }} />
                    </span>
                    <span className="w-24 shrink-0 text-right font-mono text-xs tabular-nums text-muted-foreground">{c.stats.totalLeads} leads</span>
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

/** People who wrote back and are waiting for an answer, newest first. Clear hides the ones already seen. */
export function RepliedLeads() {
  const list = useInboxList({ ...emptyFilter(), needsReply: true });
  const cleared = useCleared("replies");
  const all = (list.data?.items ?? []).filter((item) => item.lastDirection === "inbound");
  const shown = all.filter((item) => cleared.isNew(item.lastMessageAt)).slice(0, 6);
  return (
    <section aria-labelledby="replied-title" className="grid min-w-0 content-start gap-3 rounded-lg border border-border bg-surface p-5 shadow-raised">
      <PanelHead id="replied-title" title="Leads who replied" count={shown.length}
        action={shown.length > 0
          ? <Button size="sm" variant="ghost" onClick={cleared.clear}>Clear</Button>
          : cleared.clearedAt && all.length > 0 ? <Button size="sm" variant="ghost" onClick={cleared.showAll}>Show all</Button> : null} />
      {list.isLoading ? (
        <p className="text-sm text-muted-foreground">Loading</p>
      ) : shown.length === 0 ? (
        <p className="flex items-center gap-2 rounded-md bg-surface-muted px-4 py-3 text-sm text-muted-foreground"><MessageSquareReply className="size-4" aria-hidden /> No new replies</p>
      ) : (
        <ul className="grid gap-1">
          {shown.map((item) => (
            <li key={item.id}>
              <Link to={`/inbox?conversation=${encodeURIComponent(item.id)}`} className="flex min-h-12 items-center gap-3 rounded-md px-2 py-1.5 transition-colors duration-150 hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                <UserAvatar name={item.leadName} src={item.avatarUrl ?? undefined} className="size-8" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{item.leadName}</span>
                  <span className="block truncate text-xs text-muted-foreground">{item.lastMessagePreview ?? ""}</span>
                </span>
                {item.lastMessageAt && <span className="shrink-0 text-xs text-muted-foreground">{formatRelative(item.lastMessageAt)}</span>}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
