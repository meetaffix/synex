import { Link } from "react-router-dom";
import { ArrowRight, Link2, Send, Users } from "lucide-react";
import { Logo } from "@/components/brand/Logo";
import { Illustration } from "@/components/brand/Illustration";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/AuthContext";
import { Reveal } from "@/lib/motion";

const STEPS = [
  { icon: Link2, title: "Connect LinkedIn account", text: "Sign in once. Synex keeps the session and respects daily limits." },
  { icon: Users, title: "Import your leads", text: "Upload a CSV or add people one by one." },
  { icon: Send, title: "Run a campaign", text: "Send connection requests and follow-ups inside working hours." },
];

/** Shown once, right after sign-up: what Synex does and the first thing to do. */
export function WelcomePage() {
  const { user } = useAuth();
  const first = (user?.fullName ?? "").split(" ")[0];
  return (
    <main className="grid min-h-dvh bg-background text-foreground">
      <div className="relative overflow-hidden bg-brand px-4 py-10 text-brand-text sm:px-8 sm:py-14">
        <span aria-hidden className="pointer-events-none absolute -right-20 -top-20 size-72 rounded-full bg-brand-accent/10" />
        <div className="relative mx-auto grid max-w-3xl gap-6">
          <Logo size={32} />
          <div className="grid gap-3">
            <h1 className="text-2xl font-semibold">{first ? `Welcome to Synex, ${first}` : "Welcome to Synex"}</h1>
            <p className="max-w-xl text-base text-brand-text-muted">Your workspace is ready. Three steps take you from nothing to your first campaign.</p>
          </div>
        </div>
      </div>
      <div className="mx-auto grid w-full max-w-3xl content-start gap-8 px-4 py-10 sm:px-8">
        <ol className="grid gap-4 sm:grid-cols-3">
          {STEPS.map((step, index) => (
            <Reveal as="li" key={step.title} index={index} className="grid content-start gap-3 rounded-lg border border-border bg-surface p-4 shadow-raised sm:p-6">
              <span aria-hidden className="grid size-10 place-items-center rounded-full bg-primary-soft text-primary-soft-foreground">
                <step.icon className="size-5" />
              </span>
              <h2 className="text-base font-semibold">{step.title}</h2>
              <p className="text-sm text-muted-foreground">{step.text}</p>
            </Reveal>
          ))}
        </ol>
        <div className="flex flex-wrap items-center gap-4">
          <Button asChild>
            <Link to="/linkedin-accounts?connect=1">
              Connect LinkedIn account
              <ArrowRight />
            </Link>
          </Button>
          <Link to="/dashboard" className="rounded-sm text-sm font-medium text-primary underline underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            Go to the dashboard first
          </Link>
        </div>
        <Illustration name="onboarding" className="hidden h-32 justify-self-end sm:block" />
      </div>
    </main>
  );
}
