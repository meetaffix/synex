import { type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  PenLine,
  FileText,
  ArrowUpRight,
  Plus,
  AlertCircle,
} from "lucide-react";
import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
import { cn } from "@/lib/utils";
import { statusLabel, formatDate, type Post, type Account } from "./data";

export function Header({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return <PageHeader title={title} description={description} actions={action} />;
}

const STATUS_VARIANT: Record<string, BadgeProps["variant"]> = {
  connected: "success",
  published: "success",
  healthy: "success",
  configured: "success",
  scheduled: "info",
  publishing: "info",
  failed: "danger",
  needs_review: "warning",
  reconnect_required: "warning",
  not_running: "warning",
};

const DOT: Record<string, string> = { success: "bg-success", info: "bg-info", danger: "bg-danger", warning: "bg-warning", muted: "bg-muted-foreground" };

/** The same status pill as the rest of the app: a soft tint, a dot, and the label. */
export function Status({ value }: { value: string }) {
  const variant = STATUS_VARIANT[value] ?? "muted";
  return (
    <Badge variant={variant} className="shrink-0">
      <span aria-hidden className={cn("size-2 rounded-full", DOT[variant ?? "muted"])} />
      {statusLabel(value)}
    </Badge>
  );
}

export function Notice({ children, tone = "warning" }: { children: ReactNode; tone?: "warning" | "danger" | "info" }) {
  const tones = { warning: "bg-warning-soft text-warning", danger: "bg-danger-soft text-danger", info: "bg-info-soft text-info" };
  return (
    <div role={tone === "danger" ? "alert" : undefined} className={cn("flex items-start gap-3 rounded-lg p-4 text-sm [&_a]:underline [&_button]:underline", tones[tone])}>
      <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export function Empty({
  title,
  children,
}: {
  title: string;
  children?: ReactNode;
}) {
  return <EmptyState illustration="templates" title={title} action={children} />;
}

export function Load({
  error,
  loading,
}: {
  error: Error | null;
  loading: boolean;
}) {
  return error ? (
    <Notice tone="danger">
      The workspace could not be loaded. {error.message}{" "}
      <button type="button" onClick={() => window.location.reload()}>
        Try again
      </button>
    </Notice>
  ) : loading ? (
    <div role="status" aria-label="Loading the workspace" className="grid gap-3 rounded-lg border border-border bg-surface p-4 sm:p-6">
      {[0, 1, 2].map((row) => (
        <Skeleton key={row} className="h-10 w-full" />
      ))}
    </div>
  ) : null;
}
export function CreateLink() {
  return (
    <Button asChild>
      <Link to="/others/publishing/studio?new=1">
        <Plus />
        Create post
      </Link>
    </Button>
  );
}
export function Profile({ account }: { account: Account }) {
  return (
    <div className="profile-line">
      {account.picture ? (
        <img src={account.picture} alt="" referrerPolicy="no-referrer" />
      ) : (
        <span className="profile-placeholder">{account.name.slice(0, 1)}</span>
      )}
      <div>
        <strong>{account.name}</strong>
        <small>{account.email || "LinkedIn member"}</small>
      </div>
    </div>
  );
}

export function PostRows({ posts, zone }: { posts: Post[]; zone?: string }) {
  return (
    <div className="post-list">
      {posts.map((p) => (
        <Link to={`/others/publishing/studio?id=${p.id}`} className="post-row" key={p.id}>
          <div className="post-row-icon">
            <FileText size={18} />
          </div>
          <div className="post-row-main">
            <strong>
              {p.title || p.body.slice(0, 65) || "Untitled draft"}
            </strong>
            <small>
              {p.error ||
                (p.scheduledAt
                  ? formatDate(p.scheduledAt, zone)
                  : "Edited " + formatDate(p.updatedAt, zone))}
            </small>
          </div>
          <Status value={p.status} />
          <ArrowUpRight size={16} className="row-arrow" />
        </Link>
      ))}
    </div>
  );
}

export function ZoneList() {
  return (
    <datalist id="timezones">
      {[
        "UTC",
        "Europe/Amsterdam",
        "Europe/London",
        "America/New_York",
        "America/Chicago",
        "America/Los_Angeles",
        "Asia/Kolkata",
        "Asia/Singapore",
        "Australia/Sydney",
      ].map((z) => (
        <option key={z} value={z} />
      ))}
    </datalist>
  );
}
