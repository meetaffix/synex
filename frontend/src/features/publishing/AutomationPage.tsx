import { Link } from "react-router-dom";
import { Linkedin, CalendarDays, Check } from "lucide-react";
import { usePosts, useAccounts, usePreferences, type Account } from "./data";
import { Header, Notice, Empty, Load, CreateLink, PostRows } from "./shared";

export function AutomationPage() {
  const posts = usePosts(),
    accounts = useAccounts(),
    prefs = usePreferences();
  const rows = (posts.data ?? []).filter(
    (p) => p.status !== "draft" && p.status !== "published",
  );
  return (
    <>
      <Header
        title="Queue"
        description="Approved publishing jobs, with a clear status at every step."
        action={<CreateLink />}
      />
      <div className="workflow-summary">
        <div>
          <Check size={18} />
          <span>Review & approve</span>
        </div>
        <span>→</span>
        <div>
          <CalendarDays size={18} />
          <span>Persistent schedule</span>
        </div>
        <span>→</span>
        <div>
          <Linkedin size={18} />
          <span>Official API publishing</span>
        </div>
      </div>
      <Load error={posts.error || accounts.error} loading={posts.isLoading} />
      <section className="section">
        <div className="section-heading">
          <h2>Publishing queue</h2>
          <span className="muted">
            Open a job to pause, cancel, or reschedule
          </span>
        </div>
        {rows.length ? (
          rows.map((p) => (
            <div key={p.id}>
              <PostRows posts={[p]} zone={prefs.data?.timezone} />
              <div className="job-meta">
                {accounts.data?.find((a) => a.id === p.accountId)?.name ??
                  "Account unavailable"}{" "}
                · {p.attempts} publishing attempts · Requires w_member_social
              </div>
            </div>
          ))
        ) : (
          <Empty title="No pending publishing jobs">
            <p>Schedule a reviewed post to create your first job.</p>
            <Link to="/others/publishing/studio">Open content studio →</Link>
          </Empty>
        )}
      </section>
      <Notice>
        Connection requests, direct messages, scraping, and automated engagement
        are not executed by this app.{" "}
        <Link to="/campaigns">View preserved campaign records</Link> or{" "}
        <a href="https://www.linkedin.com/" target="_blank" rel="noreferrer">
          open LinkedIn for manual actions
        </a>
        .
      </Notice>
    </>
  );
}
