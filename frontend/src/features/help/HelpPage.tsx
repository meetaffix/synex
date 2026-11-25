import { Link } from "react-router-dom";
import { PageHeader } from "@/components/shared/PageHeader";

const topics = [
  {
    title: "Connect LinkedIn account",
    body: "Open Sender accounts and choose Connect LinkedIn account. Sign in with the email or phone number you use on LinkedIn. Synex uses your password once to sign in and never saves it. If LinkedIn sends a code, enter it in the same window. If it asks you to approve the sign-in in the LinkedIn app, approve it there and the window continues on its own.",
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
    title: "Build a campaign",
    body: "Open Campaigns and choose New campaign. Pick a sender, pick or add a list of leads, then build the sequence on the map: press Add action and choose each step. The sequence starts empty, so nothing is added for you. Use the Assistant at the top right to have it written for you; it prepares the sequence and you confirm it. Nothing is sent until you launch from the last step.",
  },
  {
    title: "People who are already your connections",
    body: "If a list holds only people you are already connected to, such as My connections, Synex does not offer a connection request, an If connection wait, withdraw invite or InMail. Start with a message instead. The wand icon next to a message rewrites what you wrote so it sounds more like a person, and keeps your variables. Undo puts your text back.",
  },
  {
    title: "A running campaign",
    body: "Click a campaign in the list to see its counts, what is happening now and next, each lead's progress, and to pause or resume it. Edit sequence lets you change a running campaign: changes apply to people who have not reached those steps, they are saved only when you press Save changes, and a step someone is on right now cannot be removed.",
  },
  {
    title: "Why the inbox may look empty",
    body: "A sender account can keep only conversations with people Synex has contacted, or all of its LinkedIn conversations. With the first, other chats are read and not kept, and the empty inbox says how many. Change it on the sender account's page under conversation sync.",
  },
  {
    title: "Plan and usage",
    body: "Settings shows your plan and what it includes. Limits such as the assistant's monthly minutes come from your plan, are checked by the server, and cannot be set higher than the plan allows. Changing plan is not available yet because billing is not built.",
  },
  {
    title: "Audit log",
    body: "Settings, Audit log lists actions on LinkedIn, changes the assistant made, and settings changes, newest first. It can be exported as a CSV. A workspace admin can delete the whole log by typing DELETE; one line then remains saying who cleared it and how many entries went. Campaigns, leads and limits are not affected.",
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
        Looking for posting? It lives under <Link className="text-primary-ink underline underline-offset-4" to="/others">Others</Link>.
      </p>
    </div>
  );
}
