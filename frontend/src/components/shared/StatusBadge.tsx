import { Badge, type BadgeProps } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type {
  LeadStatus,
  CampaignStatus,
  LinkedInAccountStatus,
  ConversationStatus,
} from "@/types";

type Variant = NonNullable<BadgeProps["variant"]>;

const LEAD_MAP: Record<LeadStatus, { label: string; variant: Variant }> = {
  new: { label: "New", variant: "muted" },
  contacted: { label: "Contacted", variant: "default" },
  connected: { label: "Connected", variant: "secondary" },
  replied: { label: "Replied", variant: "warning" },
  interested: { label: "Interested", variant: "success" },
  not_interested: { label: "Not interested", variant: "muted" },
  bounced: { label: "Bounced", variant: "destructive" },
};

const CAMPAIGN_MAP: Record<CampaignStatus, { label: string; variant: Variant }> =
  {
    draft: { label: "Draft", variant: "muted" },
    active: { label: "Active", variant: "success" },
    paused: { label: "Paused", variant: "warning" },
    completed: { label: "Completed", variant: "secondary" },
  };

const ACCOUNT_MAP: Record<
  LinkedInAccountStatus,
  { label: string; variant: Variant }
> = {
  pending: { label: "Awaiting pairing", variant: "warning" },
  active: { label: "Connected", variant: "success" },
  connected: { label: "Connected", variant: "success" },
  needs_reconnect: { label: "Needs reconnect", variant: "warning" },
  restricted: { label: "Restricted", variant: "destructive" },
  paused: { label: "Paused", variant: "warning" },
  warming: { label: "Warming up", variant: "default" },
  disconnected: { label: "Disconnected", variant: "muted" },
  error: { label: "Error", variant: "destructive" },
  session_expired: { label: "Session expired", variant: "warning" },
  proxy_error: { label: "Proxy error", variant: "destructive" },
};

const CONVO_MAP: Record<ConversationStatus, { label: string; variant: Variant }> =
  {
    active: { label: "Active", variant: "default" },
    interested: { label: "Interested", variant: "success" },
    not_interested: { label: "Not interested", variant: "muted" },
    archived: { label: "Archived", variant: "secondary" },
  };

interface StatusDotProps {
  variant: Variant;
  /** A gentle pulse on something that is running right now. */
  live?: boolean;
}

function StatusDot({ variant, live }: StatusDotProps) {
  const color: Record<Variant, string> = {
    default: "bg-primary",
    secondary: "bg-muted-foreground",
    outline: "bg-muted-foreground",
    success: "bg-success",
    warning: "bg-warning",
    destructive: "bg-danger",
    danger: "bg-danger",
    info: "bg-info",
    muted: "bg-muted-foreground",
  };
  return (
    <span
      className={cn("h-2 w-2 rounded-full", color[variant], live && "animate-pulse-ring")}
      aria-hidden
    />
  );
}

interface StatusBadgeProps {
  kind: "lead" | "campaign" | "account" | "conversation";
  status: string;
  withDot?: boolean;
  className?: string;
}

export function StatusBadge({
  kind,
  status,
  withDot = true,
  className,
}: StatusBadgeProps) {
  const map =
    kind === "lead"
      ? LEAD_MAP
      : kind === "campaign"
        ? CAMPAIGN_MAP
        : kind === "account"
          ? ACCOUNT_MAP
          : CONVO_MAP;
  const entry = (map as Record<string, { label: string; variant: Variant }>)[
    status
  ] ?? { label: status, variant: "muted" as Variant };

  return (
    <Badge variant={entry.variant} className={className}>
      {withDot && <StatusDot variant={entry.variant} live={kind === "campaign" && status === "active"} />}
      {entry.label}
    </Badge>
  );
}
