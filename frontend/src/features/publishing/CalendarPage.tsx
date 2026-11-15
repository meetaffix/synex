import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { usePosts, usePreferences, dayKey, type Post } from "./data";
import { Header, Empty, Load, CreateLink, PostRows } from "./shared";

export function CalendarPage() {
  const posts = usePosts(),
    prefs = usePreferences();
  const [month, setMonth] = useState(
      () => new Date(new Date().getFullYear(), new Date().getMonth(), 1),
    ),
    [selected, setSelected] = useState("");
  const zone = prefs.data?.timezone ?? "UTC",
    year = month.getFullYear(),
    m = month.getMonth();
  const offset = (new Date(year, m, 1).getDay() + 6) % 7,
    count = new Date(year, m + 1, 0).getDate();
  const scheduled = (posts.data ?? []).filter(
    (p) =>
      p.scheduledAt &&
      [
        "scheduled",
        "retrying",
        "published",
        "paused",
        "failed",
        "needs_review",
        "publishing",
      ].includes(p.status),
  );
  const key = (d: number) =>
    `${year}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
  const list = scheduled
    .filter(
      (p) => !selected || dayKey(new Date(p.scheduledAt!), zone) === selected,
    )
    .sort((a, b) => a.scheduledAt!.localeCompare(b.scheduledAt!));
  return (
    <>
      <Header
        title="Calendar"
        description={`Your publishing rhythm, in ${zone}.`}
        action={<CreateLink />}
      />
      <Load error={posts.error} loading={posts.isLoading} />
      <div className="calendar-toolbar">
        <div className="inline-actions">
          <Button
            variant="outline"
            size="icon"
            aria-label="Previous month"
            onClick={() => {
              setMonth(new Date(year, m - 1, 1));
              setSelected("");
            }}
          >
            <ChevronLeft />
          </Button>
          <h2>
            {month.toLocaleDateString(undefined, {
              month: "long",
              year: "numeric",
            })}
          </h2>
          <Button
            variant="outline"
            size="icon"
            aria-label="Next month"
            onClick={() => {
              setMonth(new Date(year, m + 1, 1));
              setSelected("");
            }}
          >
            <ChevronRight />
          </Button>
        </div>
        <Button
          variant="outline"
          onClick={() => {
            setMonth(
              new Date(new Date().getFullYear(), new Date().getMonth(), 1),
            );
            setSelected(dayKey(new Date(), zone));
          }}
        >
          Today
        </Button>
      </div>
      <div className="calendar-grid">
        {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => (
          <div className="calendar-day-name" key={d}>
            {d}
          </div>
        ))}
        {Array.from({ length: offset }, (_, i) => (
          <div className="calendar-blank" key={`b${i}`} />
        ))}
        {Array.from({ length: count }, (_, i) => i + 1).map((d) => {
          const rows = scheduled.filter(
            (p) => dayKey(new Date(p.scheduledAt!), zone) === key(d),
          );
          return (
            <button
              className={`calendar-cell ${selected === key(d) ? "selected-day" : ""} ${dayKey(new Date(), zone) === key(d) ? "today" : ""}`}
              key={d}
              onClick={() => setSelected(key(d))}
            >
              <span>{d}</span>
              {rows.slice(0, 2).map((p) => (
                <span className={`calendar-post state-${p.status}`} key={p.id}>
                  {p.title || p.body.slice(0, 25) || "Post"}
                </span>
              ))}
              {rows.length > 2 && <small>+{rows.length - 2} more</small>}
              {/* No aria-label: the name is built from what is shown, so it always contains it (WCAG 2.5.3). */}
              <span className="sr-only">{`${key(d)}: ${rows.length} ${rows.length === 1 ? "post" : "posts"}`}</span>
            </button>
          );
        })}
      </div>
      <section className="section">
        <div className="section-heading">
          <h2>{selected ? `Posts on ${selected}` : "Scheduled content"}</h2>
          {selected && (
            <Button variant="ghost" onClick={() => setSelected("")}>
              Show all
            </Button>
          )}
        </div>
        {list.length ? (
          <PostRows posts={list} zone={zone} />
        ) : (
          <Empty title="Nothing scheduled here">
            <p>Choose a draft in Content studio to add it to your calendar.</p>
            <Link to="/others/publishing/studio">Open content studio →</Link>
          </Empty>
        )}
      </section>
    </>
  );
}
