import { Link } from "react-router-dom";
import { Logo } from "@/components/brand/Logo";

/** Public privacy notice. Plain words; the assistant section is the disclosure the panel links to. */
export function PrivacyPage() {
  return (
    <div className="min-h-dvh bg-background text-foreground">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-4">
          <Link to="/" aria-label="Synex home">
            <Logo />
          </Link>
          <Link to="/login" className="text-sm text-primary-ink underline underline-offset-2">
            Sign in
          </Link>
        </div>
      </header>
      <main id="main-content" className="mx-auto grid max-w-3xl gap-8 px-4 py-8">
        <div className="space-y-2">
          <h1 className="text-2xl font-semibold">Privacy</h1>
          <p className="text-sm text-muted-foreground">How Synex handles your data. This page is short on purpose.</p>
        </div>

        <section aria-labelledby="assistant" className="grid gap-3">
          <h2 id="assistant" className="text-xl font-semibold">The assistant</h2>
          <p className="text-sm">
            When you use the assistant, what you say or type, and the workspace details it needs to answer (names and counts of your campaigns, lists, sender accounts and, when you ask about one, a lead's stored details), are processed by Deepgram, which runs speech recognition and speech, and by the language model provider Deepgram uses to write the replies.
          </p>
          <ul className="list-disc space-y-2 pl-5 text-sm">
            <li>Synex stores no audio. Your microphone is open only while you hold to talk or while hands-free is on, and a red Recording label shows it.</li>
            <li>Your words are stored only if an admin turns on conversation history in Settings. You can clear your own history there at any time.</li>
            <li>The assistant never sees passwords, LinkedIn cookies, tokens or proxy details.</li>
            <li>Synex asks Deepgram not to use your data to improve its models.</li>
            <li>Every action the assistant takes is logged for your workspace admins, with personal details left out. It changes nothing until you press Confirm.</li>
            <li>An admin can turn the assistant off for the workspace and set a monthly minute limit.</li>
          </ul>
        </section>

        <section aria-labelledby="data" className="grid gap-3">
          <h2 id="data" className="text-xl font-semibold">Your workspace data</h2>
          <p className="text-sm">
            Leads, messages and sender-account sessions stay in your workspace and are visible only to its members, according to their roles. Synex does not sell personal data.
          </p>
        </section>
      </main>
    </div>
  );
}
