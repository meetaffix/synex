import { Link } from "react-router-dom";
import { Puzzle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Header, Load } from "./shared";

export function ExtensionPage() {
  return (
    <>
      <Header
        title="Browser companion"
        description="Keep your writing workflow close, wherever you work."
      />
      <section className="extension-intro">
        <Puzzle size={32} />
        <h2>One workspace. Two ways in.</h2>
        <p>
          Use Synex in your browser, or open the companion to capture an idea
          and send it to Content studio. LinkedIn sign-in and publishing
          authorization use the same official flow.
        </p>
        <div className="inline-actions">
          <Button asChild>
            <Link to="/others/publishing/connections">Connect LinkedIn</Link>
          </Button>
          <Button variant="outline" asChild>
            <Link to="/others/publishing/studio">Open content studio</Link>
          </Button>
        </div>
      </section>
      <section className="section">
        <h2>Install the local extension</h2>
        <ol className="instructions">
          <li>
            Open your browser’s Extensions page and enable Developer mode.
          </li>
          <li>
            Select “Load unpacked” and choose the project’s{" "}
            <code>extension</code> folder.
          </li>
          <li>
            Pin Synex, open its popup, and set the workspace URL to this app’s
            address.
          </li>
          <li>
            Write an idea and choose “Open in Content studio.” Sign in if
            prompted, then save your draft.
          </li>
        </ol>
        <p className="footnote">
          The companion does not read LinkedIn cookies or scrape pages.
          Scheduling runs in the server worker and does not depend on the
          extension staying open.
        </p>
      </section>
    </>
  );
}
