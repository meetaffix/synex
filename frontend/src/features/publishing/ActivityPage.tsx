import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { useActivity, usePreferences, formatDate } from "./data";
import { Header, Status, Empty, Load } from "./shared";

export function ActivityPage() {
  const activity = useActivity(),
    prefs = usePreferences();
  return (
    <>
      <Header
        title="Activity"
        description="The record of your drafts, approvals, and publishing results."
      />
      <Load error={activity.error} loading={activity.isLoading} />
      <section className="section">
        {!!activity.data?.length && (
        <div className="post-list">
        {activity.data.map((e) => (
          <Link
            className="activity-row"
            to={`/others/publishing/studio?id=${e.postId}`}
            key={e.id}
          >
            <Status value={e.status} />
            <div>
              <strong>{e.detail}</strong>
              <small>{formatDate(e.createdAt, prefs.data?.timezone)}</small>
            </div>
            <ArrowUpRight size={16} className="row-arrow" />
          </Link>
        ))}
        </div>
        )}
        {activity.data?.length === 0 && (
          <Empty title="No activity yet">
            <p>Save a draft to start your publishing history.</p>
          </Empty>
        )}
      </section>
      <p className="footnote">Latest 200 events in this workspace.</p>
    </>
  );
}
