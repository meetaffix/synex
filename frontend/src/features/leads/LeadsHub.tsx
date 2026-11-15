import { useSearchParams } from "react-router-dom";
import { TabNav } from "@/components/shared/TabNav";
import { LeadListsPage } from "./LeadListsPage";
import { LeadsPage } from "./LeadsPage";

const tabs = [
  { id: "contacts", label: "Contacts", to: "/leads" },
  { id: "lists", label: "Lists", to: "/leads?tab=lists" },
] as const;

/** One Leads entry: contacts and the lists that group them, as two tabs. */
export function LeadsHub() {
  const [params] = useSearchParams();
  const active = params.get("tab") === "lists" ? "lists" : "contacts";
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6">
      <TabNav label="Leads sections" tabs={tabs.map((tab) => ({ label: tab.label, to: tab.to, current: tab.id === active }))} />
      <div className="min-w-0">{active === "lists" ? <LeadListsPage /> : <LeadsPage />}</div>
    </div>
  );
}
