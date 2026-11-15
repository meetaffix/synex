import { useState, type ReactNode } from "react";
import { Inbox, LayoutDashboard, MoreHorizontal, Plus, Search, Send, Users } from "lucide-react";
import { useThemeChoice } from "@/app/ThemeProvider";
import type { ThemeChoice } from "@/lib/theme";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Progress } from "@/components/ui/progress";
import { Radio } from "@/components/ui/radio";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { SortableHead, Table, TableBody, TableCell, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { toast } from "@/components/ui/sonner";
import { Illustration, type IllustrationName } from "@/components/brand/Illustration";
import { Logo, LogoMark } from "@/components/brand/Logo";
import { Sparkline } from "@/components/charts/Sparkline";
import { ProgressRing } from "@/components/charts/ProgressRing";
import { AvatarStack, UserAvatar } from "@/components/ui/avatar";
import { ChangeIndicator } from "@/features/dashboard/MetricCards";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { TabNav } from "@/components/shared/TabNav";
import { cn } from "@/lib/utils";

/** Development only: every token and every component, in every state, in the current theme. */

const COLOURS: [string, string][] = [
  ["background", "The page"],
  ["surface", "Cards, dialogs, menus"],
  ["surface-muted", "Hover rows, fills"],
  ["border", "Decorative lines"],
  ["border-strong", "Heavier dividers"],
  ["input", "Field boundaries"],
  ["foreground", "Text"],
  ["muted-foreground", "Text muted"],
  ["subtle", "Text subtle"],
  ["primary", "Primary"],
  ["primary-hover", "Primary hover"],
  ["primary-foreground", "On primary"],
  ["primary-soft", "Primary soft"],
  ["primary-soft-foreground", "On primary soft"],
  ["success", "Success"],
  ["success-soft", "Success tint"],
  ["warning", "Warning"],
  ["warning-soft", "Warning tint"],
  ["danger", "Danger"],
  ["danger-soft", "Danger tint"],
  ["info", "Info"],
  ["info-soft", "Info tint"],
  ["accent", "Warm accent"],
  ["accent-soft", "Accent tint"],
  ["brand-from", "Gradient start"],
  ["brand-to", "Gradient end"],
  ["brand-accent", "Warm highlight on gradient"],
  ["ring", "Focus ring"],
];

const TYPE = [
  { className: "text-display font-semibold tabular-nums", label: "Hero metric 36/40, 600, tabular (dashboard hero only)" },
  { className: "text-2xl font-semibold", label: "Page title 24/32, 600" },
  { className: "text-xl font-semibold", label: "Dialog title 20/28, 600" },
  { className: "text-base font-semibold", label: "Section title 16/24, 600" },
  { className: "text-sm", label: "Body 14/20, 400" },
  { className: "text-sm font-medium", label: "Label 14/20, 500" },
  { className: "text-xs font-medium text-muted-foreground", label: "Caption and table header 12/16, 500" },
];

/** Forced states for display: what hover, focus and press look like without a pointer. */
const FOCUS = "ring-2 ring-ring ring-offset-2 ring-offset-background";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={`design-${title}`} className="grid gap-4">
      <h2 id={`design-${title}`} className="text-base font-semibold">
        {title}
      </h2>
      {children}
    </section>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-2 sm:grid-cols-[8rem_minmax(0,1fr)] sm:items-center">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <div className="flex flex-wrap items-center gap-3">{children}</div>
    </div>
  );
}

export function DesignPage() {
  const { choice, setChoice } = useThemeChoice();
  const [dialog, setDialog] = useState(false);
  const [sheet, setSheet] = useState(false);
  const [on, setOn] = useState(true);
  const [sort, setSort] = useState<"asc" | "desc">("asc");

  return (
    <div className="min-h-dvh bg-background text-foreground">
      <main className="mx-auto grid max-w-screen-xl gap-12 px-4 py-8 lg:px-8">
        <PageHeader
          title="Design system"
          description="Every token and component, in the current theme. The reference is docs/DESIGN.md."
          actions={
            <div className="grid gap-2">
              <Label htmlFor="design-theme">Theme</Label>
              <NativeSelect id="design-theme" value={choice} onChange={(event) => setChoice(event.target.value as ThemeChoice)} className="w-48">
                <option value="system">Match my device</option>
                <option value="light">Light</option>
                <option value="dark">Dark</option>
              </NativeSelect>
            </div>
          }
        />

        <Section title="Colour">
          <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
            {COLOURS.map(([name, use]) => (
              <li key={name} className="grid gap-2">
                <span className="h-12 rounded-md border border-border" style={{ background: `rgb(var(--${name}))` }} />
                <span className="text-sm font-medium">{name}</span>
                <span className="text-xs text-muted-foreground">{use}</span>
              </li>
            ))}
          </ul>
        </Section>

        <Section title="Brand">
          <Row label="Logo">
            <Logo size={32} />
            <LogoMark size={32} />
            <span className="rounded-lg bg-brand p-4 text-brand-text">
              <Logo size={28} />
            </span>
          </Row>
          <Row label="Gradient">
            <div className="grid h-24 w-full max-w-md content-end rounded-lg bg-brand p-4 text-brand-text">
              <span className="text-sm text-brand-text-muted">Brand moments only</span>
              <span className="text-display font-semibold tabular-nums text-brand-accent">16.3%</span>
            </div>
          </Row>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            {(["accounts", "campaigns", "inbox", "leads", "lists", "templates", "onboarding", "success", "error"] as IllustrationName[]).map((name) => (
              <figure key={name} className="grid justify-items-center gap-2 rounded-lg border border-border bg-surface p-4">
                <Illustration name={name} />
                <figcaption className="text-xs text-muted-foreground">{name}</figcaption>
              </figure>
            ))}
          </div>
        </Section>

        <Section title="Data display">
          <Row label="Sparkline">
            <Sparkline values={[4, 6, 5, 9, 8, 12, 11, 16]} />
            <Sparkline values={[4, 6, 5, 9, 8, 12, 11, 16]} tone="accent" />
            <Sparkline values={[4, 6, 5, 9, 8, 12, 11, 16]} tone="info" />
          </Row>
          <Row label="Change">
            <ChangeIndicator values={[10, 13]} unit="weekly" />
            <ChangeIndicator values={[13, 10]} unit="weekly" />
            <ChangeIndicator values={[10, 10]} unit="weekly" />
          </Row>
          <Row label="Progress ring">
            <ProgressRing done={0} total={4} />
            <ProgressRing done={2} total={4} />
            <ProgressRing done={4} total={4} />
          </Row>
          <Row label="Avatars">
            {["Ada Lovelace", "Grace Hopper", "Jordan Morgan", "Priya Raman", "Sam Lee"].map((name) => (
              <UserAvatar key={name} name={name} className="size-10" />
            ))}
            <AvatarStack people={["Ada Lovelace", "Grace Hopper", "Jordan Morgan", "Priya Raman", "Sam Lee"].map((name) => ({ name }))} />
          </Row>
          <Row label="Raised card">
            <div className="grid w-64 gap-1 rounded-lg border border-border bg-surface p-4 shadow-raised transition-transform duration-200 hover:-translate-y-0.5">
              <span className="text-sm text-muted-foreground">Hover me</span>
              <span className="text-2xl font-semibold">1,204</span>
            </div>
          </Row>
        </Section>

        <Section title="Type">
          <div className="grid gap-3">
            {TYPE.map((item) => (
              <p key={item.label} className={item.className}>
                {item.label}
              </p>
            ))}
            <p className="text-sm">Tabular figures: 1,204 · 98.5% · 3,110</p>
          </div>
        </Section>

        <Section title="Radius and space">
          <Row label="Radius">
            {[
              ["rounded-sm", "8 inputs"],
              ["rounded-md", "12 buttons, menus"],
              ["rounded-lg", "16 cards, dialogs"],
              ["rounded-full", "full pills"],
            ].map(([radius, label]) => (
              <span key={radius} className={cn("grid h-16 w-28 place-items-center border border-border-strong bg-surface text-xs", radius)}>
                {label}
              </span>
            ))}
          </Row>
          <Row label="Spacing">
            {[1, 2, 3, 4, 6, 8, 12].map((step) => (
              <span key={step} className="grid justify-items-center gap-1 text-xs text-muted-foreground">
                <span className="block bg-primary" style={{ width: `var(--space-${step})`, height: `var(--space-${step})` }} />
                {step * 4}
              </span>
            ))}
          </Row>
        </Section>

        <Section title="Buttons">
          {(["default", "secondary", "ghost", "danger", "link"] as const).map((variant) => (
            <Row key={variant} label={variant === "default" ? "Primary" : variant[0].toUpperCase() + variant.slice(1)}>
              <Button variant={variant}>Connect LinkedIn account</Button>
              <Button variant={variant} className={variant === "default" ? "bg-primary-hover" : variant === "link" ? "text-primary-hover" : "bg-surface-muted"}>
                Hover
              </Button>
              <Button variant={variant} className={FOCUS}>
                Focus
              </Button>
              <Button variant={variant} className="scale-[0.98]">
                Pressed
              </Button>
              <Button variant={variant} disabled>
                Disabled
              </Button>
              <Button variant={variant} loading>
                Saving
              </Button>
            </Row>
          ))}
          <Row label="Sizes">
            <Button size="sm" variant="secondary">
              Compact 36
            </Button>
            <Button>Default 40</Button>
            <Button size="icon" variant="ghost" aria-label="More actions">
              <MoreHorizontal />
            </Button>
            <Button size="icon-sm" variant="ghost" aria-label="Add">
              <Plus />
            </Button>
          </Row>
        </Section>

        <Section title="Fields">
          <div className="grid gap-6 md:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor="d-default">Email or phone</Label>
              <Input id="d-default" placeholder="name@company.com" />
              <p className="text-xs text-muted-foreground">Help text sits under the field.</p>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="d-focus">Focused</Label>
              <Input id="d-focus" defaultValue="ada@example.com" className={FOCUS} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="d-invalid">Invalid</Label>
              <Input id="d-invalid" defaultValue="not an email" aria-invalid aria-describedby="d-invalid-help" />
              <p id="d-invalid-help" className="text-xs text-danger">
                Enter an email address or a phone number.
              </p>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="d-disabled">Disabled</Label>
              <Input id="d-disabled" defaultValue="Read only" disabled />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="d-native">Native select</Label>
              <NativeSelect id="d-native" defaultValue="all">
                <option value="all">All conversations</option>
                <option value="active">Active</option>
              </NativeSelect>
            </div>
            <div className="grid gap-2">
              <Label id="d-select-label">Select</Label>
              <Select defaultValue="new">
                <SelectTrigger aria-labelledby="d-select-label">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="new">New</SelectItem>
                  <SelectItem value="contacted">Contacted</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2 md:col-span-2">
              <Label htmlFor="d-textarea">Notes (optional)</Label>
              <Textarea id="d-textarea" placeholder="Add context, intro details or reminders" />
            </div>
          </div>
          <Row label="Checkbox">
            <label className="flex items-center gap-2 text-sm">
              <Checkbox /> Off
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox defaultChecked /> On
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox checked="indeterminate" /> Some
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox disabled /> Disabled
            </label>
          </Row>
          <Row label="Radio">
            <label className="flex items-center gap-2 text-sm">
              <Radio name="d-radio" defaultChecked /> Only Synex conversations
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Radio name="d-radio" /> All conversations
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Radio name="d-radio-2" disabled /> Disabled
            </label>
          </Row>
          <Row label="Switch">
            <span className="flex items-center gap-2 text-sm">
              <Switch checked={on} onCheckedChange={setOn} aria-label="Pause on failure" /> Pause on failure
            </span>
            <span className="flex items-center gap-2 text-sm">
              <Switch checked={false} onCheckedChange={() => undefined} disabled aria-label="Disabled switch" /> Disabled
            </span>
          </Row>
          <Row label="Progress">
            <Progress value={24} aria-label="Actions today" className="w-48" />
          </Row>
        </Section>

        <Section title="Status pills and badges">
          <Row label="Status">
            <StatusBadge kind="account" status="connected" />
            <StatusBadge kind="account" status="needs_reconnect" />
            <StatusBadge kind="account" status="restricted" />
            <StatusBadge kind="campaign" status="draft" />
            <StatusBadge kind="lead" status="contacted" />
          </Row>
          <Row label="Badges">
            <Badge>Primary</Badge>
            <Badge variant="success">Success</Badge>
            <Badge variant="warning">Warning</Badge>
            <Badge variant="danger">Danger</Badge>
            <Badge variant="info">Info</Badge>
            <Badge variant="muted">Neutral</Badge>
          </Row>
        </Section>

        <Section title="Card, metric card and filter bar">
          <div className="grid gap-4 md:grid-cols-3">
            <Card>
              <CardHeader>
                <CardTitle>Card title</CardTitle>
                <CardDescription>Surface, 1px border, 16 radius, 24 padding.</CardDescription>
              </CardHeader>
              <CardContent className="text-sm">Content follows the header.</CardContent>
            </Card>
            <div className="grid gap-2 rounded-lg border border-border bg-surface p-4 sm:p-6">
              <span className="text-sm text-muted-foreground">Connections accepted</span>
              <span className="text-2xl font-semibold">1,204</span>
            </div>
            <div className="grid gap-2 rounded-lg border border-border bg-surface p-4 sm:p-6">
              <span className="text-sm text-muted-foreground">Median response time</span>
              <span className="text-sm text-muted-foreground">Not available yet</span>
            </div>
          </div>
          <form aria-label="Filters" className="flex flex-wrap gap-4" onSubmit={(event) => event.preventDefault()}>
            <div className="grid gap-2">
              <Label htmlFor="d-search">Search</Label>
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
                <Input id="d-search" className="w-64 pl-9" placeholder="Name or company" />
              </div>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="d-range">Date range</Label>
              <NativeSelect id="d-range" className="w-48" defaultValue="all">
                <option value="all">All time</option>
                <option value="30">Last 30 days</option>
              </NativeSelect>
            </div>
          </form>
        </Section>

        <Section title="Table">
          <div className="rounded-lg border border-border bg-surface">
            <Table regionLabel="Example table">
              <TableHeader>
                <TableRow>
                  <SortableHead label="Name" active direction={sort} onSort={() => setSort(sort === "asc" ? "desc" : "asc")} />
                  <SortableHead label="Status" active={false} direction="asc" onSort={() => undefined} />
                  <SortableHead label="Leads" active={false} direction="asc" onSort={() => undefined} align="right" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {(sort === "asc" ? ["Q4 outreach", "Webinar invite"] : ["Webinar invite", "Q4 outreach"]).map((name, index) => (
                  <TableRow key={name} data-state={index === 1 ? "selected" : undefined}>
                    <TableCell className="font-medium">{name}</TableCell>
                    <TableCell>
                      <StatusBadge kind="campaign" status={index ? "paused" : "active"} />
                    </TableCell>
                    <TableCell className="text-right">{index ? "48" : "1,210"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </Section>

        <Section title="Navigation">
          <TabNav label="Example tabs" tabs={[{ label: "Contacts", to: "/design", current: true }, { label: "Lists", to: "/design?tab=lists", current: false }]} />
          <Row label="Sidebar item">
            <div className="grid w-60 gap-1 rounded-lg border border-border bg-surface p-3">
              <span className="flex min-h-10 items-center gap-3 rounded-md bg-primary-soft px-3 text-sm font-medium text-primary-soft-foreground">
                <LayoutDashboard className="size-4" aria-hidden /> Dashboard (active)
              </span>
              <span className="flex min-h-10 items-center gap-3 rounded-md px-3 text-sm font-medium text-muted-foreground">
                <Inbox className="size-4" aria-hidden /> Inbox
              </span>
              <span className="flex min-h-10 items-center gap-3 rounded-md bg-surface-muted px-3 text-sm font-medium text-foreground">
                <Send className="size-4" aria-hidden /> Campaigns (hover)
              </span>
            </div>
          </Row>
        </Section>

        <Section title="Overlays">
          <Row label="Open">
            <Button variant="secondary" onClick={() => setDialog(true)}>
              Dialog
            </Button>
            <Button variant="secondary" onClick={() => setSheet(true)}>
              Sheet
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="secondary">Dropdown menu</Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                <DropdownMenuItem>Edit</DropdownMenuItem>
                <DropdownMenuItem>Pause sending</DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem className="text-danger focus:text-danger">Disconnect</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="secondary">Tooltip</Button>
              </TooltipTrigger>
              <TooltipContent>Building campaigns comes next</TooltipContent>
            </Tooltip>
            <Button variant="secondary" onClick={() => toast.success("Account connected. Synex will start sending in working hours.")}>
              Toast
            </Button>
          </Row>
          <Dialog open={dialog} onOpenChange={setDialog}>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Disconnect Ada Lovelace?</DialogTitle>
                <DialogDescription>Synex stops sending from this account and forgets its session. Leads and results are kept.</DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="secondary" onClick={() => setDialog(false)}>
                  Cancel
                </Button>
                <Button variant="danger" onClick={() => setDialog(false)}>
                  Disconnect
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
          <Sheet open={sheet} onOpenChange={setSheet}>
            <SheetContent className="p-6">
              <SheetTitle className="text-base font-semibold">Sheet</SheetTitle>
              <SheetDescription className="mt-2 text-sm text-muted-foreground">Navigation on phones and tablets.</SheetDescription>
            </SheetContent>
          </Sheet>
        </Section>

        <Section title="Empty state, skeleton, avatar">
          <EmptyState
            icon={Users}
            title="No leads yet"
            description="Leads are the people your campaigns contact. Add one, or import a CSV with their LinkedIn URLs."
            action={<Button>Add lead</Button>}
          />
          <Row label="Skeleton">
            <div role="status" aria-label="Loading example" className="grid w-full max-w-md gap-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-2/3" />
            </div>
          </Row>
          <Row label="Avatar">
            <Avatar>
              <AvatarFallback>AL</AvatarFallback>
            </Avatar>
            <Avatar className="size-10">
              <AvatarFallback>GH</AvatarFallback>
            </Avatar>
          </Row>
        </Section>
      </main>
    </div>
  );
}
