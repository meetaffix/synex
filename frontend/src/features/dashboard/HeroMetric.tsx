import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { Sparkline } from "@/components/charts/Sparkline";
import { Skeleton } from "@/components/ui/skeleton";
import { useCountUp } from "@/lib/motion";
import { formatNumber } from "@/utils/format";
import { changeOf, describeChange } from "./insights";

interface Props {
  /** Replies and leads contacted, when the dashboard has them. */
  replies: number | null;
  contacted: number | null;
  /** Reply rate per period, newest last, for the trend. */
  rates: number[];
  unit: "weekly" | "daily";
  loading: boolean;
}

/** The one number that matters most: how many of the people Synex contacted wrote back. A brand moment, so it gets the gradient. */
export function HeroMetric({ replies, contacted, rates, unit, loading }: Props) {
  const rate = replies !== null && contacted ? (replies / contacted) * 100 : null;
  const counted = useCountUp(rate === null ? null : Math.round(rate * 10), 800);
  const change = changeOf(rates.map((value) => Math.round(value * 10) / 10));
  const Icon = !change ? Minus : change.delta > 0 ? ArrowUpRight : change.delta < 0 ? ArrowDownRight : Minus;

  return (
    <section aria-labelledby="hero-title" className="relative grid min-w-0 content-between gap-6 overflow-hidden rounded-lg bg-brand p-6 text-brand-text shadow-raised sm:p-8">
      <span aria-hidden className="pointer-events-none absolute -right-16 -top-16 size-56 rounded-full bg-brand-accent/10" />
      <h2 id="hero-title" className="relative text-sm font-medium text-brand-text-muted">
        Reply rate
      </h2>
      <div className="relative flex flex-wrap items-end justify-between gap-6">
        <div className="grid gap-2">
          {loading ? (
            <Skeleton className="h-8 w-32 bg-brand-text/10" />
          ) : rate === null ? (
            <>
              <p className="text-xl font-semibold">Not available yet</p>
              <p className="max-w-xs text-sm text-brand-text-muted">It shows once Synex has sent messages and people have answered.</p>
            </>
          ) : (
            <p className="text-display font-semibold tabular-nums text-brand-accent">
              <span className="sr-only">{rate.toFixed(1)} percent</span>
              <span aria-hidden>{((counted ?? Math.round(rate * 10)) / 10).toFixed(1)}%</span>
            </p>
          )}
          {rate !== null && replies !== null && contacted !== null && (
            <p className="text-sm text-brand-text-muted">
              {formatNumber(replies)} {replies === 1 ? "reply" : "replies"} from {formatNumber(contacted)} {contacted === 1 ? "lead" : "leads"} contacted
            </p>
          )}
          {change && (
            <p className="inline-flex items-center gap-1 text-sm font-medium text-brand-text">
              <Icon className="size-4" aria-hidden />
              {describeChange(change, unit, " pts")}
            </p>
          )}
        </div>
        {rates.length > 1 && <Sparkline values={rates} width={180} height={64} tone="brand" />}
      </div>
    </section>
  );
}
