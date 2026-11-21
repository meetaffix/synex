import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/services/client";

interface PlanInfo {
  plan: string; name: string; limits: { assistantMinutes: number };
  seats: { used: number; limit: number | null };
  assistantMinutes: { used: number; limit: number; month: string };
  plans: { id: string; name: string; assistantMinutes: number; seats: number | null; dailyInvites: number | null; dailyMessages: number | null; dailyVisits: number | null; current: boolean }[];
  canManage: boolean; upgradeAvailable: boolean; upgradeNote: string;
}

/** The plan and what it includes, read from the server. Changing plan is said plainly to be unavailable: billing is not built. */
export function PlanCard() {
  const { data, isLoading, isError, refetch } = useQuery({ queryKey: ["plan"], queryFn: () => api.get<PlanInfo>("/plan"), retry: false });
  if (isLoading) return <Skeleton className="h-40 w-full" aria-label="Loading your plan" />;
  if (isError || !data) return <Card><CardHeader><CardTitle>Plan</CardTitle><CardDescription role="alert">Your plan could not be loaded.</CardDescription></CardHeader><CardContent><Button variant="secondary" onClick={() => void refetch()}>Try again</Button></CardContent></Card>;
  const percent = data.assistantMinutes.limit === 0 ? 100 : Math.min(100, (data.assistantMinutes.used / data.assistantMinutes.limit) * 100);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Plan: {data.name}</CardTitle>
        <CardDescription>What your plan includes, and how much of it you have used this month.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="grid gap-2" data-testid="plan-seats">
          <div className="flex items-baseline justify-between gap-3">
            <p className="text-sm font-medium">LinkedIn accounts</p>
            <p className="text-sm text-muted-foreground">{data.seats.used} of {data.seats.limit ?? "unlimited"} in use</p>
          </div>
          <Progress value={data.seats.limit ? Math.min(100, (data.seats.used / data.seats.limit) * 100) : 0} aria-label={`${data.seats.used} of ${data.seats.limit ?? "unlimited"} LinkedIn accounts in use`} />
        </div>
        <div className="grid gap-2" data-testid="plan-usage">
          <div className="flex items-baseline justify-between gap-3">
            <p className="text-sm font-medium">Assistant minutes</p>
            <p className="text-sm text-muted-foreground">{data.assistantMinutes.used} of {data.assistantMinutes.limit} used in {data.assistantMinutes.month}</p>
          </div>
          <Progress value={percent} aria-label={`${data.assistantMinutes.used} of ${data.assistantMinutes.limit} assistant minutes used this month`} />
        </div>
        <ul aria-label="Plans" className="grid gap-2 text-sm sm:grid-cols-2 xl:grid-cols-4">
          {data.plans.map((p) => (
            <li key={p.id} className={`grid content-start gap-0.5 rounded-lg border px-3 py-3 ${p.current ? "border-primary bg-primary-soft shadow-raised" : "border-border"}`}>
              <span className="font-semibold">{p.name}{p.current && <span className="text-xs font-normal text-muted-foreground"> (yours)</span>}</span>
              <span className="text-xs text-muted-foreground">{p.seats} LinkedIn account{p.seats === 1 ? "" : "s"}</span>
              <span className="text-xs text-muted-foreground">Per account a day: {p.dailyInvites} requests, {p.dailyMessages} messages, {p.dailyVisits} visits</span>
              <span className="text-xs text-muted-foreground">{p.assistantMinutes} assistant minutes a month</span>
              {p.id === "enterprise" && <span className="text-xs text-muted-foreground">Limits can be unlocked for your team.</span>}
            </li>
          ))}
        </ul>
        <p role="note" className="text-sm text-muted-foreground">{data.upgradeNote}</p>
        <div><Button variant="outline" disabled title={data.upgradeNote}>Change plan (not available yet)</Button></div>
      </CardContent>
    </Card>
  );
}
