import { useSenderAccounts } from "@/features/linkedin-accounts/hooks";
import { cn } from "@/lib/utils";

/** Synex's signature: how much of today's safe campaign budget is used, wherever Synex is about to act.
    Counts only accounts that can send now; the limit is today's, after warm-up. */
export function TodayBudget({ accountId, className }: { accountId?: string | null; className?: string }) {
  const accounts = useSenderAccounts();
  const live = (accounts.data ?? []).filter((a) => (accountId ? a.id === accountId : a.status === "connected"));
  if (!live.length) return null;
  const used = live.reduce((sum, a) => sum + a.dailyActionsUsed, 0);
  const limit = live.reduce((sum, a) => sum + (a.dailyActionLimitToday ?? a.dailyActionLimit), 0);
  const near = limit > 0 && used / limit >= 0.8;
  // The overall daily budget counts the work Synex does on its own (campaign steps); messages you type count against the message limit instead.
  const label = `${accountId ? `${live[0].name}: ` : ""}${used} of ${limit} campaign actions used today${accountId ? "" : " across your sender accounts"}. Messages you type yourself count against the message limit, not this budget.`;
  return (
    <span title={label} className={cn("inline-flex items-center gap-2 font-mono text-xs tabular-nums text-muted-foreground", className)}>
      <span aria-hidden className={cn("size-1.5 rounded-full", near ? "bg-warning" : "bg-primary")} />
      <span aria-hidden>{used} of {limit} today</span>
      <span className="sr-only">{label}</span>
    </span>
  );
}
