import { Link } from "react-router-dom";
import { PageHeader } from "@/components/shared/PageHeader";

const tools = [
  {
    title: "Content publishing",
    to: "/others/publishing",
    description: "Write, schedule and publish LinkedIn posts. Includes Studio, Calendar, Queue, Activity and Analytics.",
  },
];

export function OthersPage() {
  return (
    <div className="grid gap-6">
      <PageHeader title="Others" description="Secondary tools that sit outside outreach." />
      <ul className="grid gap-4 sm:grid-cols-2">
        {tools.map((tool) => (
          <li key={tool.to}>
            <Link
              to={tool.to}
              className="grid h-full gap-2 rounded-lg border border-border bg-surface p-4 shadow-raised transition-transform duration-200 hover:-translate-y-0.5 sm:p-6 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span className="text-base font-semibold">{tool.title}</span>
              <span className="text-sm text-muted-foreground">{tool.description}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
