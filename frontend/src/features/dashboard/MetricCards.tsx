import { ArrowDownRight, ArrowUpRight, Clock, MessageSquare, Minus, Send, Star, UserCheck, UserPlus, type LucideIcon } from "lucide-react";
import { Sparkline } from "@/components/charts/Sparkline";
import { Skeleton } from "@/components/ui/skeleton";
import { Reveal, useCountUp } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { formatNumber } from "@/utils/format";
import { changeOf, describeChange, type SeriesKey } from "./insights";

export type MetricKey =
  | "connectionsAccepted"
  | "leadsContacted"
  | "replies"
  | "interestedLeads"
  | "interestedAnswered"
  | "medianResponseSeconds";

/** A missing value is shown as "Not available yet", never as a made-up number. */
export type MetricValues = Record<MetricKey, number | null>;

const CARDS: { key: MetricKey; label: string; icon: LucideIcon; series?: SeriesKey }[] = [
  { key: "connectionsAccepted", label: "Connections accepted", icon: UserCheck, series: "accepted" },
  { key: "leadsContacted", label: "Leads contacted", icon: Send, series: "requests" },
  { key: "replies", label: "Replies", icon: MessageSquare, series: "replies" },
  { key: "interestedLeads", label: "Interested leads", icon: Star },
  { key: "interestedAnswered", label: "Interested leads answered", icon: UserPlus },
  { key: "medianResponseSeconds", label: "Median response time", icon: Clock },
];

export const noMetrics: MetricValues = {
  connectionsAccepted: null,
  leadsContacted: null,
  replies: null,
  interestedLeads: null,
  interestedAnswered: null,
  medianResponseSeconds: null,
};

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)} s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours < 48) return rest ? `${hours} h ${rest} min` : `${hours} h`;
  return `${Math.round(hours / 24)} days`;
}

/** Up, down or flat: an arrow and the change in words, so colour never carries it alone. */
export function ChangeIndicator({ values, unit }: { values: number[]; unit: "weekly" | "daily" }) {
  const change = changeOf(values);
  if (!change) return null;
  const Icon = change.delta > 0 ? ArrowUpRight : change.delta < 0 ? ArrowDownRight : Minus;
  return (
    <span className={cn("inline-flex items-center gap-1 text-xs font-medium", change.delta > 0 ? "text-success" : change.delta < 0 ? "text-warning" : "text-muted-foreground")}>
      <Icon className="size-3.5" aria-hidden />
      {describeChange(change, unit)}
    </span>
  );
}

function Figure({ metric, value, loading }: { metric: MetricKey; value: number | null; loading: boolean }) {
  const counted = useCountUp(metric === "medianResponseSeconds" ? null : value);
  if (loading) return <Skeleton className="h-8 w-16" />;
  if (value === null) return <span className="text-sm font-normal text-muted-foreground">Not available yet</span>;
  return <>{metric === "medianResponseSeconds" ? formatDuration(value) : formatNumber(counted ?? value)}</>;
}

interface Props {
  values: MetricValues;
  loading: boolean;
  /** Where the numbers come from, in plain words. */
  source: string;
  /** Per-period series for the sparklines and the change indicators, when the feed exists. */
  series?: Record<SeriesKey, number[]>;
  unit?: "weekly" | "daily";
}

export function MetricCards({ values, loading, source, series, unit = "weekly" }: Props) {
  return (
    <section aria-label="Key metrics" className="grid gap-3">
      <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {CARDS.map(({ key, label, icon: Icon, series: seriesKey }, index) => {
          const value = values[key];
          const trend = seriesKey ? series?.[seriesKey] ?? [] : [];
          return (
            <Reveal
              key={key}
              index={index}
              className="grid gap-3 rounded-lg border border-border bg-surface p-4 shadow-raised transition-transform duration-200 hover:-translate-y-0.5 sm:p-6"
            >
              <dt className="flex items-center justify-between gap-3 text-sm text-muted-foreground">
                {label}
                <span aria-hidden className="grid size-8 place-items-center rounded-full bg-primary-soft text-primary-soft-foreground">
                  <Icon className="size-4" />
                </span>
              </dt>
              <dd className="grid gap-2">
                <span className="flex items-end justify-between gap-3">
                  <span className="text-2xl font-semibold tracking-tight">
                    <Figure metric={key} value={value} loading={loading} />
                  </span>
                  {!loading && value !== null && trend.length > 1 && <Sparkline values={trend} width={96} height={36} />}
                </span>
                {!loading && value !== null && <span className="min-h-4"><ChangeIndicator values={trend} unit={unit} /></span>}
              </dd>
            </Reveal>
          );
        })}
      </dl>
      <p className="text-xs text-muted-foreground">{source}</p>
    </section>
  );
}
