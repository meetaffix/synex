import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/services/client";
import { Header, Status, Notice, Empty, Load } from "./shared";

export function AnalyticsPage() {
  const q = useQuery({
    queryKey: ["publishing", "metrics"],
    queryFn: () =>
      api.get<{
        counts: Record<string, number>;
        successRate: number | null;
        source: string;
      }>("/publishing/metrics"),
  });
  if (!q.data)
    return (
      <>
        <Header title="Analytics" />
        <Load error={q.error} loading={q.isLoading} />
      </>
    );
  const c = q.data?.counts ?? {};
  return (
    <>
      <Header
        title="Analytics"
        description="Publishing performance grounded in your workspace records."
      />
      <Load error={q.error} loading={q.isLoading} />
      <div className="metric-strip">
        <div>
          <span>Posts created</span>
          <strong>{Object.values(c).reduce((a, b) => a + b, 0)}</strong>
        </div>
        <div>
          <span>Published</span>
          <strong>{c.published ?? 0}</strong>
        </div>
        <div>
          <span>Publishing success rate</span>
          <strong>
            {q.data?.successRate != null ? `${q.data.successRate}%` : "—"}
          </strong>
        </div>
        <div>
          <span>Failed / unresolved</span>
          <strong>{(c.failed ?? 0) + (c.needs_review ?? 0)}</strong>
        </div>
      </div>
      <section className="section">
        <div className="section-heading">
          <h2>Content by status</h2>
          <span className="muted">All time</span>
        </div>
        {Object.entries(c).map(([s, n]) => (
          <div className="distribution-row" key={s}>
            <Status value={s} />
            <div className="distribution-track">
              <div
                style={{
                  width: `${(n / Math.max(1, ...Object.values(c))) * 100}%`,
                }}
              />
            </div>
            <strong>{n}</strong>
          </div>
        ))}
        {!Object.keys(c).length && (
          <Empty title="Your data starts with your first post">
            <p>
              Publishing activity will appear here as you use the workspace.
            </p>
            <Link to="/others/publishing/studio">Create a draft →</Link>
          </Empty>
        )}
      </section>
      <p className="footnote">{q.data?.source}</p>
      <Notice>
        LinkedIn impressions, follower counts, and engagement analytics require
        additional approved API access. They are not included in these internal
        metrics.
      </Notice>
    </>
  );
}
