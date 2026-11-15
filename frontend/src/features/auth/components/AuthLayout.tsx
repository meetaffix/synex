import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { MessageSquare, Send, Users } from "lucide-react";
import { Logo } from "@/components/brand/Logo";
import { Sparkline } from "@/components/charts/Sparkline";

const EXAMPLE_SERIES = [4, 6, 5, 9, 8, 12, 11, 16];

/** A drawn example of the product, built in HTML so it follows the theme. It is an illustration, not real data. */
function ProductPreview() {
  return (
    <div aria-hidden className="relative mx-auto w-full max-w-md">
      <div className="rounded-lg border border-brand-text/15 bg-surface p-4 text-foreground shadow-float sm:p-5">
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold">This week</span>
          <span className="rounded-full bg-success-soft px-2 py-0.5 text-xs font-medium text-success">Running</span>
        </div>
        <div className="mt-4 grid grid-cols-3 gap-3">
          {[
            { icon: Send, label: "Invites", value: "86" },
            { icon: Users, label: "Accepted", value: "38" },
            { icon: MessageSquare, label: "Replies", value: "14" },
          ].map((metric) => (
            <div key={metric.label} className="rounded-md bg-surface-muted p-3">
              <metric.icon className="size-4 text-primary" />
              <p className="mt-2 text-xl font-semibold">{metric.value}</p>
              <p className="text-xs text-muted-foreground">{metric.label}</p>
            </div>
          ))}
        </div>
        <div className="mt-4 flex items-end justify-between gap-4 rounded-md bg-primary-soft p-3">
          <div>
            <p className="text-xs text-primary-soft-foreground">Reply rate</p>
            <p className="text-2xl font-semibold text-primary-soft-foreground">16%</p>
          </div>
          <Sparkline values={EXAMPLE_SERIES} width={140} height={40} />
        </div>
      </div>
      <div className="absolute -bottom-6 -left-4 w-64 rounded-lg border border-brand-text/15 bg-surface p-3 text-foreground shadow-float max-sm:-left-0 sm:-left-8">
        <div className="flex items-center gap-3">
          <span className="grid size-8 place-items-center rounded-full bg-accent-soft text-xs font-semibold text-accent">JM</span>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">Jordan Morgan</p>
            <p className="truncate text-xs text-muted-foreground">Sounds interesting. Can we talk Thursday?</p>
          </div>
        </div>
      </div>
    </div>
  );
}

/** The first screen every person sees: the form on one side and the brand on the other. */
export function AuthLayout({ children, title, subtitle }: { children: ReactNode; title: string; subtitle: string }) {
  return (
    <div className="grid min-h-dvh grid-rows-[auto_1fr] bg-background text-foreground lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:grid-rows-1">
      {/* Phones: the brand is a header band. */}
      <header className="bg-brand px-4 py-4 text-brand-text lg:hidden">
        <Link to="/" aria-label="Synex home" className="inline-block rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-text">
          <Logo size={28} />
        </Link>
        <p className="mt-2 text-sm text-brand-text-muted">Reach the right people on LinkedIn, safely.</p>
      </header>

      <main className="flex items-start justify-center px-4 py-8 sm:px-8 sm:py-12 lg:items-center">
        <div className="grid w-full max-w-sm gap-6">
          <div className="grid gap-2">
            <h1 className="text-2xl font-semibold">{title}</h1>
            <p className="text-sm text-muted-foreground">{subtitle}</p>
          </div>
          {children}
        </div>
      </main>

      {/* Desktop: the brand panel. */}
      <aside aria-label="About Synex" className="relative hidden overflow-hidden bg-brand p-12 text-brand-text lg:flex lg:flex-col lg:justify-between">
        <span aria-hidden className="pointer-events-none absolute -right-24 -top-24 size-80 rounded-full bg-brand-accent/10" />
        <span aria-hidden className="pointer-events-none absolute -bottom-32 -left-16 size-96 rounded-full bg-brand-text/5" />
        <Link to="/" aria-label="Synex home" className="relative w-fit rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-text">
          <Logo size={32} />
        </Link>
        <div className="relative grid gap-10">
          <div className="grid max-w-md gap-3">
            <p className="text-2xl font-semibold">Reach the right people on LinkedIn, safely.</p>
            <p className="text-base text-brand-text-muted">
              Connect your accounts, run campaigns inside daily limits, and answer every reply from one inbox.
            </p>
          </div>
          <ProductPreview />
        </div>
        <p className="relative text-xs text-brand-text-muted">Example figures, for illustration.</p>
      </aside>
    </div>
  );
}
