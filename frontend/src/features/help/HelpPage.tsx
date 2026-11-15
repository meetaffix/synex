import { Link } from "react-router-dom";
import { PageHeader } from "@/components/shared/PageHeader";

const topics = [
  {
    title: "Connect a sender account",
    body: "Open Sender accounts and choose Connect account. Sign in with the email or phone number you use on LinkedIn. Synex uses your password once to sign in and never saves it. If LinkedIn sends a code, enter it in the same window. If it asks you to approve the sign-in in the LinkedIn app, approve it there and the window continues on its own.",
  },
  {
    title: "If LinkedIn asks for a security check",
    body: "Synex does not complete CAPTCHAs or other checks for you. Sign in to LinkedIn yourself in a normal browser, finish the check there, then connect the account again.",
  },
  {
    title: "Connecting an account that is not yours",
    body: "From a connected account's menu, choose Send a link so the owner reconnects it. The link works once, expires after 24 hours, and lets the owner sign in without a Synex login.",
  },
  {
    title: "Daily limits",
    body: "Each account has a daily action limit and a weekly cap on connection requests. New accounts ramp up gradually. Automating LinkedIn goes against LinkedIn's terms and accounts can be restricted, so keep limits conservative.",
  },
];

export function HelpPage() {
  return (
    <div className="grid gap-6">
      <PageHeader title="Help" description="How the main parts of Synex work." />
      <div className="grid gap-4">
        {topics.map((topic) => (
          <section key={topic.title} className="grid gap-2 rounded-lg border border-border bg-surface p-4 sm:p-6">
            <h2 className="text-base font-semibold">{topic.title}</h2>
            <p className="max-w-prose text-sm text-muted-foreground">{topic.body}</p>
          </section>
        ))}
      </div>
      <p className="text-sm text-muted-foreground">
        Looking for posting? It lives under <Link className="text-primary underline underline-offset-4" to="/others">Others</Link>.
      </p>
    </div>
  );
}
