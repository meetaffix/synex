import { Fragment, useEffect, useMemo, useState } from "react";
import { useAssistantPage } from "@/features/assistant/AssistantProvider";
import { useSearchParams } from "react-router-dom";
import {
  Plus,
  Upload,
  MoreHorizontal,
  Pencil,
  Trash2,
  ExternalLink,
  Users,
  Download,
  Tag,
  Sparkles,
  Loader2,
  CheckCircle2,
  XCircle,
  Columns3,
} from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { PageHeader } from "@/components/shared/PageHeader";
import { SearchInput } from "@/components/shared/SearchInput";
import { EmptyState } from "@/components/shared/EmptyState";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { UserAvatar } from "@/components/ui/avatar";
import { Skeleton } from "@/components/ui/skeleton";
import { useSort } from "@/hooks/useSort";
import {
  SortableHead,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { LeadFormDialog } from "./components/LeadFormDialog";
import { LeadOverviewDialog } from "./components/LeadOverviewDialog";
import { OPTIONAL_COLUMNS, useLeadColumns } from "./columns";
import { useAuth } from "@/features/auth/AuthContext";
import { AddLeadsDialog } from "./components/AddLeadsDialog";
import { useLeads, useLeadLists, useLeadMutations, useImportJobs } from "@/hooks/api";
import { leadsService } from "@/services/resources";
import { toast } from "@/components/ui/sonner";
import { toCsv } from "@/utils/csv";
import type { Lead, LeadStatus } from "@/types";

const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: "all", label: "All statuses" },
  { value: "new", label: "New" },
  { value: "contacted", label: "Contacted" },
  { value: "connected", label: "Connected" },
  { value: "replied", label: "Replied" },
  { value: "interested", label: "Interested" },
  { value: "not_interested", label: "Not interested" },
];

const PAGE_SIZE = 12;
const NO_LEADS: Lead[] = [];
const SORT_COLUMNS = {
  name: (lead: Lead) => `${lead.firstName} ${lead.lastName}`.trim(),
  company: (lead: Lead) => lead.company,
  email: (lead: Lead) => lead.email,
  title: (lead: Lead) => lead.jobTitle,
  location: (lead: Lead) => lead.location,
  phone: (lead: Lead) => lead.phone,
  industry: (lead: Lead) => lead.industry,
  status: (lead: Lead) => lead.status,
};
type SortKey = keyof typeof SORT_COLUMNS;

export function LeadsPage() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [listId, setListId] = useState("all");
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  // True when the user chose "Select all N matching" (across every page), so
  // delete targets the whole filtered set via the efficient backend endpoint.
  const [selectAllMatching, setSelectAllMatching] = useState(false);

  const [formOpen, setFormOpen] = useState(false);
  const [params, setParams] = useSearchParams();
  // "Import your leads" links here with ?import=1: open the dialog, then drop the flag so a reload does not reopen it.
  const [importOpen, setImportOpen] = useState(params.get("import") === "1");
  useEffect(() => {
    if (params.get("import") === "1") {
      params.delete("import");
      setParams(params, { replace: true });
    }
  }, [params, setParams]);
  const [editLead, setEditLead] = useState<Lead | null>(null);
  useAssistantPage(editLead ? { leadId: editLead.id } : null);
  const [deleteTarget, setDeleteTarget] = useState<Lead | null>(null);
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);

  const filters = useMemo(
    () => ({ search, status, listId }),
    [search, status, listId]
  );
  const { data: leads, isLoading, error: loadError, refetch } = useLeads(filters);
  const { data: lists } = useLeadLists();
  const { remove, bulkDelete, bulkStatus, deleteAll } = useLeadMutations();
  const { data: importJobs } = useImportJobs();

  // Reset any selection when the filter set changes — a cross-page "select all"
  // no longer makes sense against a different result set.
  const clearSelection = () => {
    setSelected(new Set());
    setSelectAllMatching(false);
  };

  const total = leads?.length ?? 0;
  const { user } = useAuth();
  const columns = useLeadColumns(user?.id);
  const filtering = search !== "" || status !== "all" || listId !== "all";
  const noLeadsAtAll = !isLoading && !loadError && total === 0 && !filtering;
  const clearFilters = () => {
    setSearch("");
    setStatus("all");
    setListId("all");
    setPage(0);
  };
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const { sorted, sort, toggle: toggleSort } = useSort(leads ?? NO_LEADS, SORT_COLUMNS, { key: "name", direction: "asc" });
  const pageLeads = useMemo(() => sorted.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE), [sorted, page]);
  const sortHead = (key: SortKey, label: string, className?: string) => (
    <SortableHead label={label} active={sort.key === key} direction={sort.direction} onSort={() => { toggleSort(key); setPage(0); }} className={className} />
  );

  const allSelected =
    pageLeads.length > 0 && pageLeads.every((l) => selected.has(l.id));
  const someSelected = pageLeads.some((l) => selected.has(l.id));

  const toggleAll = () => {
    const next = new Set(selected);
    if (allSelected) pageLeads.forEach((l) => next.delete(l.id));
    else pageLeads.forEach((l) => next.add(l.id));
    setSelected(next);
    setSelectAllMatching(false);
  };
  const toggleOne = (id: string) => {
    const next = new Set(selected);
    next.has(id) ? next.delete(id) : next.add(id);
    setSelected(next);
    setSelectAllMatching(false);
  };
  const selectAll = () => {
    setSelected(new Set((leads ?? []).map((l) => l.id)));
    setSelectAllMatching(true);
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    await remove.mutateAsync(deleteTarget.id);
    toast.success("Lead deleted");
    setDeleteTarget(null);
  };

  const handleBulkDelete = async () => {
    try {
      if (selectAllMatching) {
        const { deleted } = await deleteAll.mutateAsync(filters);
        toast.success(`Deleted ${deleted} leads`);
      } else {
        await bulkDelete.mutateAsync([...selected]);
        toast.success(`Deleted ${selected.size} leads`);
      }
      clearSelection();
      setPage(0);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not delete leads");
    } finally {
      setBulkDeleteOpen(false);
    }
  };

  const handleBulkStatus = async (s: LeadStatus) => {
    await bulkStatus.mutateAsync({ ids: [...selected], status: s });
    toast.success(`Updated ${selected.size} leads`);
    clearSelection();
  };

  const enrich = async (lead: Lead) => {
    try {
      const res = await leadsService.enrich(lead.id);
      toast.success(res.detail ?? "Enrichment queued");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not queue enrichment");
    }
  };

  const exportCsv = () => {
    const rows = (leads ?? []).map((l) => ({
      first_name: l.firstName,
      last_name: l.lastName,
      company: l.company,
      job_title: l.jobTitle,
      headline: l.headline ?? "",
      linkedin_url: l.linkedinUrl,
      email: l.email ?? "",
      phone: l.phone ?? "",
      location: l.location ?? "",
      industry: l.industry ?? "",
      connected_at: l.connectedAt ?? "",
      tags: (l.tags ?? []).join("; "),
      status: l.status,
    }));
    const blob = new Blob([toCsv(rows)], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "synex-leads.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const [overviewLead, setOverviewLead] = useState<Lead | null>(null);
  const openEdit = (lead: Lead) => {
    setEditLead(lead);
    setFormOpen(true);
  };
  const openCreate = () => {
    setEditLead(null);
    setFormOpen(true);
  };

  const activeJobs = importJobs?.filter(
    (j) => j.status === "pending" || j.status === "processing"
  ) ?? [];
  const recentDone = importJobs?.filter(
    (j) => j.status === "completed" || j.status === "failed"
  ).slice(0, 1) ?? [];

  if (loadError) return (
    <div role="alert" className="flex flex-wrap items-center gap-3 rounded-lg bg-danger-soft p-4 text-sm text-danger">
      <span>Leads could not be loaded. {loadError.message}</span>
      <Button size="sm" variant="secondary" onClick={() => refetch()}>Try again</Button>
    </div>
  );
  return (
    <div className="grid gap-6">
      {/* Persistent import progress — stays visible even when dialog is closed */}
      {(activeJobs.length > 0 || recentDone.length > 0) && (
        <div className="space-y-2">
          {activeJobs.map((job) => {
            const pct = job.totalCount
              ? Math.min(100, Math.round((job.fetchedCount / job.totalCount) * 100))
              : null;
            return (
              <div
                key={job.id}
                className="flex items-center gap-3 rounded-lg border border-border bg-surface px-4 py-3 text-sm shadow-raised"
              >
                <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span className="font-medium capitalize">
                      {job.source === "connections" ? "Importing LinkedIn connections" : `Importing from ${job.source}`}
                    </span>
                    <span className="tabular-nums text-xs text-muted-foreground">
                      {job.fetchedCount}{job.totalCount ? ` / ${job.totalCount}` : ""}
                    </span>
                  </div>
                  {pct !== null && (
                    <Progress value={pct} className="mt-2 h-2" />
                  )}
                </div>
              </div>
            );
          })}
          {activeJobs.length === 0 && recentDone.map((job) => (
            <div
              key={job.id}
              className="flex items-center gap-3 rounded-md border border-border bg-surface-muted/30 px-4 py-3 text-sm"
            >
              {job.status === "completed"
                ? <CheckCircle2 className="h-4 w-4 shrink-0 text-success" />
                : <XCircle className="h-4 w-4 shrink-0 text-danger" />}
              <span>
                {job.status === "completed"
                  ? (job.detail ?? `Import complete — ${job.createdCount} leads added`)
                  : `Import failed${job.detail ? `: ${job.detail}` : ""}`}
              </span>
            </div>
          ))}
        </div>
      )}

      <PageHeader
        title="Contacts"
        description={`${total} ${total === 1 ? "lead" : "leads"} in your workspace`}
        actions={
          noLeadsAtAll ? undefined : (
          <>
            <Button variant="outline" onClick={exportCsv}>
              <Download className="h-4 w-4" />
              Export
            </Button>
            <Button variant="outline" onClick={() => setImportOpen(true)}>
              <Upload className="h-4 w-4" />
              Add leads
            </Button>
            <Button onClick={openCreate}>
              <Plus className="h-4 w-4" />
              Add lead
            </Button>
          </>
          )
        }
      />

      {/* Filters */}
      <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-3 shadow-raised sm:flex-row sm:items-center">
        <SearchInput
          value={search}
          onChange={(v) => {
            setSearch(v);
            setPage(0);
            clearSelection();
          }}
          placeholder="Search leads"
          className="sm:max-w-xs"
        />
        <div className="flex gap-3">
          <Select
            value={status}
            onValueChange={(v) => {
              setStatus(v);
              setPage(0);
              clearSelection();
            }}
          >
            <SelectTrigger className="w-[160px]" aria-label="Filter by status">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STATUS_FILTERS.map((f) => (
                <SelectItem key={f.value} value={f.value}>
                  {f.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={listId}
            onValueChange={(v) => {
              setListId(v);
              setPage(0);
              clearSelection();
            }}
          >
            <SelectTrigger className="w-[170px]" aria-label="Filter by list">
              <SelectValue placeholder="All lists" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All lists</SelectItem>
              {lists?.map((l) => (
                <SelectItem key={l.id} value={l.id}>
                  {l.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {/* Name, Company, Email and Status always show; the rest is the person's choice, remembered for them. */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="secondary" className="hidden md:inline-flex sm:ml-auto">
              <Columns3 className="h-4 w-4" />
              Columns
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>Show columns</DropdownMenuLabel>
            {OPTIONAL_COLUMNS.map((column) => (
              <DropdownMenuCheckboxItem
                key={column.key}
                checked={columns.shows(column.key)}
                onCheckedChange={() => columns.toggle(column.key)}
                onSelect={(event) => event.preventDefault()}
              >
                {column.label}
              </DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Bulk action bar */}
      {selected.size > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-primary/30 bg-primary-soft px-4 py-3 text-primary-soft-foreground shadow-raised">
          <span className="text-sm font-medium">
            {selectAllMatching
              ? `All ${total} leads selected`
              : `${selected.size} selected`}
          </span>
          {/* Cross-page select-all: only meaningful once more than one page
              exists and the current page is fully selected. */}
          {!selectAllMatching && allSelected && total > pageLeads.length && (
            <Button
              size="sm"
              variant="link"
              className="h-auto p-0 text-xs"
              onClick={selectAll}
            >
              Select all {total}
            </Button>
          )}
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <Select onValueChange={(v) => handleBulkStatus(v as LeadStatus)}>
              <SelectTrigger className="h-8 w-[150px] text-xs" aria-label="Set status for the selected leads">
                <Tag className="h-4 w-4" />
                <SelectValue placeholder="Set status" />
              </SelectTrigger>
              <SelectContent>
                {STATUS_FILTERS.filter((s) => s.value !== "all").map((s) => (
                  <SelectItem key={s.value} value={s.value}>
                    {s.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              size="sm"
              variant="outline"
              className="text-danger hover:text-danger"
              onClick={() => setBulkDeleteOpen(true)}
            >
              <Trash2 className="h-4 w-4" />
              Delete
            </Button>
            <Button size="sm" variant="ghost" onClick={clearSelection}>
              Clear
            </Button>
          </div>
        </div>
      )}

      {/* Table */}
      <Card className="overflow-hidden shadow-raised">
        {isLoading ? (
          <div role="status" aria-label="Loading leads" className="grid gap-2 p-4 sm:p-6">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : total === 0 ? (
          <EmptyState
            illustration="leads"
            className="rounded-none border-0"
            title={filtering ? "No leads match" : "No leads yet"}
            description={
              filtering
                ? "Try a different search, or show every status and list."
                : "Leads are the people your campaigns contact. Add one, or import a CSV with their LinkedIn URLs."
            }
            action={
              filtering ? (
                <Button variant="secondary" onClick={clearFilters}>
                  Clear filters
                </Button>
              ) : (
                <>
                  <Button variant="secondary" onClick={() => setImportOpen(true)}>
                    <Upload className="h-4 w-4" />
                    Add leads
                  </Button>
                  <Button onClick={openCreate}>
                    <Plus className="h-4 w-4" />
                    Add lead
                  </Button>
                </>
              )
            }
          />
        ) : (
          <>
            <Table regionLabel="Leads" className="w-max min-w-full whitespace-nowrap">
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="w-10">
                    <Checkbox
                      checked={
                        allSelected
                          ? true
                          : someSelected
                            ? "indeterminate"
                            : false
                      }
                      onCheckedChange={toggleAll}
                      aria-label="Select all"
                    />
                  </TableHead>
                  {sortHead("name", "Name")}
                  {sortHead("company", "Company", "hidden md:table-cell")}
                  {sortHead("email", "Email", "hidden md:table-cell")}
                  {sortHead("status", "Status")}
                  {OPTIONAL_COLUMNS.filter((column) => columns.shows(column.key)).map((column) => (
                    <Fragment key={column.key}>{sortHead(column.key, column.label, "hidden md:table-cell")}</Fragment>
                  ))}
                  <TableHead className="w-10" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {pageLeads.map((lead) => (
                  <TableRow
                    key={lead.id}
                    data-state={selected.has(lead.id) ? "selected" : undefined}
                  >
                    <TableCell>
                      <Checkbox
                        checked={selected.has(lead.id)}
                        onCheckedChange={() => toggleOne(lead.id)}
                        aria-label={`Select ${lead.firstName}`}
                      />
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <UserAvatar
                          name={`${lead.firstName} ${lead.lastName}`}
                          src={lead.avatarUrl}
                        />
                        <div className="min-w-0">
                          <p className="truncate font-medium">
                            {lead.firstName} {lead.lastName}
                          </p>
                          <p className="truncate text-xs text-muted-foreground md:hidden">
                            {lead.company}
                          </p>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="hidden max-w-[16rem] truncate md:table-cell">
                      {lead.company || "—"}
                    </TableCell>
                    <TableCell className="hidden max-w-[16rem] truncate text-muted-foreground md:table-cell">
                      {lead.email || "—"}
                    </TableCell>
                    <TableCell>
                      <StatusBadge kind="lead" status={lead.status} />
                    </TableCell>
                    {columns.shows("title") && (
                      <TableCell className="hidden max-w-[16rem] truncate text-muted-foreground md:table-cell">{lead.jobTitle || lead.headline || "—"}</TableCell>
                    )}
                    {columns.shows("location") && (
                      <TableCell className="hidden max-w-[12rem] truncate text-muted-foreground md:table-cell">{lead.location || "—"}</TableCell>
                    )}
                    {columns.shows("phone") && <TableCell className="hidden text-muted-foreground md:table-cell">{lead.phone || "—"}</TableCell>}
                    {columns.shows("industry") && (
                      <TableCell className="hidden max-w-[12rem] truncate text-muted-foreground md:table-cell">{lead.industry || "—"}</TableCell>
                    )}
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${lead.firstName} ${lead.lastName}`}>
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuLabel>Actions</DropdownMenuLabel>
                          <DropdownMenuItem onClick={() => setOverviewLead(lead)}>
                            Details and campaigns
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => openEdit(lead)}>
                            <Pencil className="h-4 w-4" />
                            Edit
                          </DropdownMenuItem>
                          {lead.linkedinUrl && (
                            <DropdownMenuItem asChild>
                              <a
                                href={lead.linkedinUrl}
                                target="_blank"
                                rel="noreferrer"
                              >
                                <ExternalLink className="h-4 w-4" />
                                Open LinkedIn
                              </a>
                            </DropdownMenuItem>
                          )}
                          {lead.linkedinUrl && (
                            <DropdownMenuItem disabled title="Requires an approved data provider">
                              <Sparkles className="h-4 w-4" />
                              Enrich from LinkedIn
                            </DropdownMenuItem>
                          )}
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            destructive
                            onClick={() => setDeleteTarget(lead)}
                          >
                            <Trash2 className="h-4 w-4" />
                            Delete
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            {/* Pagination */}
            <div className="flex items-center justify-between border-t border-border bg-surface-muted/40 px-4 py-3 text-sm">
              <p className="text-muted-foreground">
                Showing {page * PAGE_SIZE + 1}–
                {Math.min((page + 1) * PAGE_SIZE, total)} of {total}
              </p>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page === 0}
                  onClick={() => setPage((p) => p - 1)}
                >
                  Previous
                </Button>
                <span className="text-muted-foreground">
                  {page + 1} / {pageCount}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page >= pageCount - 1}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </Button>
              </div>
            </div>
          </>
        )}
      </Card>

      <LeadFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        lead={editLead}
      />
      <AddLeadsDialog open={importOpen} onOpenChange={setImportOpen} />
      <LeadOverviewDialog lead={overviewLead} onClose={() => setOverviewLead(null)} />
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        title="Delete lead?"
        description={`This will permanently remove ${deleteTarget?.firstName} ${deleteTarget?.lastName} from your workspace.`}
        confirmLabel="Delete"
        destructive
        loading={remove.isPending}
        onConfirm={handleDelete}
      />
      <ConfirmDialog
        open={bulkDeleteOpen}
        onOpenChange={setBulkDeleteOpen}
        title={`Delete ${selectAllMatching ? total : selected.size} leads?`}
        description={
          selectAllMatching
            ? "Every lead matching the current filters will be permanently removed. This cannot be undone."
            : "This action cannot be undone."
        }
        confirmLabel="Delete all"
        destructive
        loading={bulkDelete.isPending || deleteAll.isPending}
        onConfirm={handleBulkDelete}
      />
    </div>
  );
}
