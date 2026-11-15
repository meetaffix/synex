import { AlertCircle, Linkedin } from "lucide-react";
import { config } from "@/services/client";
import { Button } from "@/components/ui/button";

/** Why a LinkedIn sign-in came back without signing the person in, and what to do next. */
const REASONS: Record<string, string> = {
  not_configured: "LinkedIn sign-in is not set up for this workspace yet. Continue with your email, or ask your administrator.",
  link_existing: "This email already has a Synex account. Sign in with your email, then link LinkedIn from Settings.",
  email_required: "LinkedIn did not share a verified email. Create an account with your email, then link LinkedIn from Settings.",
  failed: "LinkedIn did not finish the sign-in. Try again, or continue with your email.",
};

export function SocialButtons() {
  const reason = new URLSearchParams(window.location.search).get("linkedin");
  return (
    <div className="grid gap-3">
      <Button className="w-full" variant="secondary" asChild>
        <a href={`${config.API_URL}/linkedin/login`}>
          <Linkedin />
          Continue with LinkedIn
        </a>
      </Button>
      {reason && (
        <p role="alert" className="flex items-start gap-2 rounded-lg bg-danger-soft p-3 text-sm text-danger">
          <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
          {REASONS[reason] ?? "The LinkedIn sign-in did not complete. Try again, or continue with your email."}
        </p>
      )}
    </div>
  );
}

export function AuthDivider() {
  return (
    <div className="flex items-center gap-3 text-xs text-muted-foreground">
      <span aria-hidden className="h-px flex-1 bg-border" />
      or use your email
      <span aria-hidden className="h-px flex-1 bg-border" />
    </div>
  );
}
