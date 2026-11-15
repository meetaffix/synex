import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Linkedin, ArrowUpRight, Clock3 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/services/client";
import {
  usePosts,
  useAccounts,
  useActivity,
  usePreferences,
  formatDate,
} from "./data";
import {
  Header,
  Status,
  Empty,
  Load,
  CreateLink,
  Profile,
  PostRows,
} from "./shared";

export function Overview() {
  const posts = usePosts(),
    accounts = useAccounts(),
    activity = useActivity(),
    prefs = usePreferences();
  const metrics = useQuery({
    queryKey: ["publishing", "metrics"],
    queryFn: () =>
      api.get<{
        counts: Record<string, number>;
        successRate: number | null;
        source: string;
      }>("/publishing/metrics"),
  });
  if (!posts.data || !accounts.data || !metrics.data)
    return (
      <>
        <Header title="Overview" />
        <Load
          error={posts.error || accounts.error || metrics.error}
          loading={posts.isLoading || accounts.isLoading || metrics.isLoading}
        />
      </>
    );
  const counts = metrics.data?.counts ?? {};
  const upcoming = (posts.data ?? [])
    .filter((p) => ["scheduled", "retrying"].includes(p.status))
    .sort((a, b) => (a.scheduledAt ?? "").localeCompare(b.scheduledAt ?? ""))
    .slice(0, 5);
  const issues = (posts.data ?? []).filter((p) =>
    ["failed", "needs_review"].includes(p.status),
  );
  return (
    <>
      <Header
        title="Overview"
        description="A clear view of what’s ready, what’s next, and what needs you."
        action={<CreateLink />}
      />
      <Load
        error={posts.error || accounts.error || metrics.error}
        loading={posts.isLoading || accounts.isLoading}
      />
      {accounts.data?.length === 0 && (
        <div className="onboarding">
          <div>
            <div className="step-label">Get started</div>
            <h2>Bring your LinkedIn into the workspace.</h2>
            <p>
              Connect your account to turn drafts into a consistent publishing
              schedule.
            </p>
            <Button asChild>
              <Link to="/others/publishing/connections">
                <Linkedin />
                Connect LinkedIn
              </Link>
            </Button>
          </div>
          <ol>
            <li>
              <span>1</span>Authorize your LinkedIn account
            </li>
            <li>
              <span>2</span>Write and preview your first post
            </li>
            <li>
              <span>3</span>Choose when it goes live
            </li>
          </ol>
        </div>
      )}
      {!!accounts.data?.length && (
        <div className="account-strip">
          <Profile account={accounts.data[0]} />
          <Status value={accounts.data[0].status} />
          <span className="muted">
            Checked {formatDate(accounts.data[0].checkedAt)}
          </span>
          <Link to="/others/publishing/connections">
            Manage accounts <ArrowUpRight size={14} />
          </Link>
        </div>
      )}
      <div className="metric-strip">
        {[
          ["Scheduled", (counts.scheduled ?? 0) + (counts.retrying ?? 0)],
          ["Published", counts.published ?? 0],
          ["Drafts", counts.draft ?? 0],
          ["Need attention", (counts.failed ?? 0) + (counts.needs_review ?? 0)],
        ].map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{metrics.isLoading ? "—" : value}</strong>
          </div>
        ))}
      </div>
      <div className="overview-columns">
        <section className="section">
          <div className="section-heading">
            <h2>Coming up next</h2>
            <Link to="/others/publishing/calendar">
              View calendar <ArrowUpRight size={14} />
            </Link>
          </div>
          {upcoming.length ? (
            <PostRows posts={upcoming} zone={prefs.data?.timezone} />
          ) : (
            <Empty title="Your schedule is clear">
              <p>Start with a draft. Publish when you’re ready.</p>
              <Link to="/others/publishing/studio?new=1">Write a post →</Link>
            </Empty>
          )}
        </section>
        <section className="section">
          <div className="section-heading">
            <h2>Recent activity</h2>
            <Link to="/others/publishing/activity">View all</Link>
          </div>
          <Load error={activity.error} loading={activity.isLoading} />
          {!!activity.data?.length && (
          <div className="post-list">
          {activity.data.slice(0, 5).map((e) => (
            <Link
              to={`/others/publishing/studio?id=${e.postId}`}
              className="activity-row"
              key={e.id}
            >
              <span className="activity-dot" />
              <div>
                <strong>{e.detail}</strong>
                <small>{formatDate(e.createdAt, prefs.data?.timezone)}</small>
              </div>
            </Link>
          ))}
          </div>
          )}
          {activity.data?.length === 0 && (
            <div className="quiet-empty">
              <Clock3 size={22} />
              <p>Your publishing history will appear here.</p>
            </div>
          )}
        </section>
      </div>
      {issues.length > 0 && (
        <section className="section">
          <div className="section-heading">
            <h2>Needs your attention</h2>
            <span>{issues.length} {issues.length === 1 ? "post" : "posts"}</span>
          </div>
          <PostRows posts={issues} />
        </section>
      )}
    </>
  );
}
