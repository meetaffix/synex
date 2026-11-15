import { useCallback, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/features/auth/AuthContext";
import { useCampaignList } from "@/features/campaigns/hooks";
import { useSenderAccounts } from "@/features/linkedin-accounts/hooks";
import { leadsService } from "@/services/resources";

export interface Step {
  id: "account" | "leads" | "campaign" | "launch";
  title: string;
  detail: string;
  done: boolean;
  /** Where the step starts. A step whose flow does not exist in the app yet has no action, only a note. */
  action?: { label: string; to: string };
  note?: string;
}

const key = (userId: string | undefined) => `synex.onboarding.dismissed.${userId ?? "signed-out"}`;

function readDismissed(userId: string | undefined) {
  try {
    return localStorage.getItem(key(userId)) === "1";
  } catch {
    return false;
  }
}

/** The four first-run steps, worked out from what the person already has. Nothing is stored except "dismissed". */
export function useOnboarding() {
  const { user } = useAuth();
  const accounts = useSenderAccounts();
  const campaigns = useCampaignList();
  const leads = useQuery({ queryKey: ["onboarding", "leads"], queryFn: () => leadsService.list(), staleTime: 30_000 });
  const [dismissed, setDismissed] = useState(() => readDismissed(user?.id));

  const loading = accounts.isLoading || campaigns.isLoading || leads.isLoading;
  const hasAccount = (accounts.data?.length ?? 0) > 0;
  const hasLeads = (leads.data?.length ?? 0) > 0;
  const hasCampaign = (campaigns.data?.length ?? 0) > 0;
  const launched = (campaigns.data ?? []).some((campaign) => campaign.status === "active" || campaign.status === "completed");

  const steps: Step[] = [
    { id: "account", title: "Connect LinkedIn account", detail: "Sign in once; Synex keeps the session and sends within safe daily limits.", done: hasAccount, action: { label: "Connect LinkedIn account", to: "/linkedin-accounts?connect=1" } },
    { id: "leads", title: "Import your leads", detail: "Upload a CSV with their LinkedIn URLs, or add people one at a time.", done: hasLeads, action: { label: "Import leads", to: "/leads?import=1" } },
    {
      id: "campaign",
      title: "Create a campaign",
      detail: "A sequence of steps, such as a connection request and a follow-up message.",
      done: hasCampaign,
      note: "Building campaigns in the app comes next. Existing campaigns appear on the Campaigns page.",
      action: { label: "View campaigns", to: "/campaigns" },
    },
    { id: "launch", title: "Launch it", detail: "Synex starts contacting leads inside working hours.", done: launched, note: hasCampaign ? undefined : "Available once a campaign exists." },
  ];
  const doneCount = steps.filter((step) => step.done).length;
  const complete = doneCount === steps.length;

  const dismiss = useCallback(() => {
    try {
      localStorage.setItem(key(user?.id), "1");
    } catch {
      /* a convenience only */
    }
    setDismissed(true);
  }, [user?.id]);

  return { steps, doneCount, complete, loading, dismissed, dismiss, firstOpen: steps.find((step) => !step.done) };
}
