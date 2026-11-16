import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { api } from "@/services/client";
import { requestFailureMessage } from "@/features/linkedin-accounts/copy";
import { useState } from "react";

/** Opening the builder starts a draft right away, so it can save as you go. It needs no sender and no leads. */
export function NewCampaignPage() {
  const navigate = useNavigate();
  const started = useRef(false);
  const [error, setError] = useState<string>();
  const start = () => {
    setError(undefined);
    api.post<{ id: string }>("/campaigns", { action: "create", name: "Untitled campaign", timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC" })
      .then((created) => navigate(`/campaigns/${created.id}/edit`, { replace: true }))
      .catch((e) => setError(requestFailureMessage(e)));
  };
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    start();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  if (error) {
    return (
      <div role="alert" className="grid gap-3 rounded-lg border border-danger/40 bg-danger-soft p-4 text-sm text-danger">
        <p>The campaign could not be started. {error}</p>
        <div><Button size="sm" variant="outline" onClick={start}>Try again</Button></div>
      </div>
    );
  }
  return <p role="status" className="text-sm text-muted-foreground">Starting a new campaign.</p>;
}
