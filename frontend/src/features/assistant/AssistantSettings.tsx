import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { FormField } from "@/components/shared/FormField";
import { assistantService, type AssistantSettings as Settings } from "./service";

const IDLE_CHOICES = [60, 120, 300, 600, 900];

/** Workspace settings for the assistant: on or off, the monthly minute cap and meter, idle timeout, history. */
export function AssistantSettings() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError, refetch } = useQuery({ queryKey: ["assistant", "settings"], queryFn: assistantService.settings });
  const [cap, setCap] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: assistantService.updateSettings,
    onSuccess: (next) => {
      queryClient.setQueryData(["assistant", "settings"], next);
      setCap(null);
      toast.success("Assistant settings saved");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const clear = useMutation({
    mutationFn: assistantService.clearHistory,
    onSuccess: () => toast.success("Your assistant history was cleared"),
    onError: (error: Error) => toast.error(error.message),
  });

  if (isLoading) return <Skeleton role="status" className="h-64 w-full" aria-label="Loading assistant settings" />;
  if (isError || !data)
    return (
      <Card>
        <CardHeader>
          <CardTitle>Assistant</CardTitle>
          <CardDescription role="alert">Assistant settings could not load.</CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="secondary" onClick={() => void refetch()}>
            Try again
          </Button>
        </CardContent>
      </Card>
    );

  const s: Settings = data;
  const used = Math.round(s.usedSeconds / 60);
  const percent = s.monthlyMinuteCap === 0 ? 100 : Math.min(100, (s.usedSeconds / (s.monthlyMinuteCap * 60)) * 100);
  const readOnly = !s.canEdit;
  const capValue = cap ?? String(s.monthlyMinuteCap);
  const capNumber = Number(capValue);
  const capInvalid = capValue.trim() === "" || !Number.isInteger(capNumber) || capNumber < 0 || capNumber > 10000;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Assistant</CardTitle>
        <CardDescription>Talk or type to plan, draft and set up outreach. It prepares changes; you confirm each one.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6">
        {!s.available && (
          <p role="status" className="rounded-md bg-warning-soft px-3 py-2 text-sm text-warning">
            The voice service key is not set on the server yet, so the assistant cannot start.
          </p>
        )}
        {readOnly && <p className="text-sm text-muted-foreground">Only a workspace admin can change these settings.</p>}

        <div className="flex items-center justify-between gap-4">
          <div>
            <p id="assistant-enabled-label" className="text-sm font-medium">Turn on the assistant for this workspace</p>
            <p className="text-sm text-muted-foreground">When off, the button still opens the panel but explains it is off, and no sessions start.</p>
          </div>
          <Switch aria-labelledby="assistant-enabled-label" checked={s.enabled} disabled={readOnly || save.isPending} onCheckedChange={(enabled) => save.mutate({ enabled })} />
        </div>

        <div className="grid gap-2" data-testid="usage-meter">
          <div className="flex items-baseline justify-between gap-3">
            <p className="text-sm font-medium">Usage this month</p>
            <p className="text-sm text-muted-foreground">
              {used} of {s.monthlyMinuteCap} minutes used
            </p>
          </div>
          <Progress value={percent} aria-label={`${used} of ${s.monthlyMinuteCap} assistant minutes used this month`} indicatorClassName={s.capReached ? "bg-danger" : undefined} />
          {s.capReached && (
            <p role="alert" className="text-sm text-danger">
              The monthly limit is reached, so the assistant is paused until next month or until the limit is raised.
            </p>
          )}
        </div>

        <form
          className="grid gap-4 sm:grid-cols-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (!capInvalid) save.mutate({ monthlyMinuteCap: capNumber });
          }}
        >
          <FormField label="Monthly minute limit" help="0 turns the assistant off. Time is counted while a session is open." error={capInvalid ? "Enter a whole number from 0 to 10000." : undefined}>
            <Input type="number" min={0} max={10000} value={capValue} disabled={readOnly} onChange={(e) => setCap(e.target.value)} />
          </FormField>
          <FormField label="End a session after">
            <NativeSelect value={s.idleTimeoutSeconds} disabled={readOnly || save.isPending} onChange={(e) => save.mutate({ idleTimeoutSeconds: Number(e.target.value) })}>
              {[...new Set([...IDLE_CHOICES, s.idleTimeoutSeconds])].sort((a, b) => a - b).map((seconds) => (
                <option key={seconds} value={seconds}>
                  {seconds < 60 ? `${seconds} seconds` : `${seconds / 60} minute${seconds === 60 ? "" : "s"}`} of inactivity
                </option>
              ))}
            </NativeSelect>
          </FormField>
          <FormField label="Speech recognition language">
            <NativeSelect value={s.language} disabled={readOnly || save.isPending} onChange={(e) => save.mutate({ language: e.target.value as Settings["language"] })}>
              <option value="en">English</option>
              <option value="en-IN">English (India)</option>
            </NativeSelect>
          </FormField>
          <div className="sm:col-span-3">
            <Button type="submit" variant="secondary" disabled={readOnly || capInvalid || capValue === String(s.monthlyMinuteCap)} loading={save.isPending}>
              Save limit
            </Button>
          </div>
        </form>

        <div className="flex items-center justify-between gap-4">
          <div>
            <p id="assistant-history-label" className="text-sm font-medium">Keep conversation history</p>
            <p className="text-sm text-muted-foreground">Off by default. When on, the words of your conversations are stored so you can read them later. Audio is never stored.</p>
          </div>
          <Switch aria-labelledby="assistant-history-label" checked={s.historyEnabled} disabled={readOnly || save.isPending} onCheckedChange={(historyEnabled) => save.mutate({ historyEnabled })} />
        </div>
        <div>
          <Button variant="secondary" size="sm" loading={clear.isPending} onClick={() => clear.mutate()}>
            Clear my history
          </Button>
        </div>

        <p className="text-xs text-muted-foreground">
          Voice and workspace data are processed by Deepgram and the language model it uses. Synex stores no audio.{" "}
          <Link to="/privacy" className="text-primary underline underline-offset-2">
            Read the privacy notice
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}
