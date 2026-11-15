import { Outlet } from "react-router-dom";
import { TabNav } from "@/components/shared/TabNav";

const sections = [
  { label: "Overview", to: "/others/publishing", end: true },
  { label: "Studio", to: "/others/publishing/studio" },
  { label: "Calendar", to: "/others/publishing/calendar" },
  { label: "Queue", to: "/others/publishing/queue" },
  { label: "Activity", to: "/others/publishing/activity" },
  { label: "Analytics", to: "/others/publishing/analytics" },
  { label: "Connections", to: "/others/publishing/connections" },
];

/** Content publishing is a secondary tool, so its pages share one section nav inside Others. */
export function PublishingLayout() {
  return (
    <div className="grid gap-6">
      <TabNav label="Content publishing" tabs={sections} />
      <Outlet />
    </div>
  );
}
