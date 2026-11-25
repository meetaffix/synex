import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Plus,
  ListChecks,
  MoreHorizontal,
  Pencil,
  Trash2,
  ArrowRight,
  Download,
  Search,
} from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { EmptyState } from "@/components/shared/EmptyState";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useLeadLists, useLeadListMutations } from "@/hooks/api";
import { NativeSelect } from "@/components/ui/native-select";
import { api } from "@/services/client";
import { toast } from "@/components/ui/sonner";
import { cn } from "@/lib/utils";
import type { LeadList } from "@/types";

/** List colours are theme tokens, so they follow the palette. Older lists may hold a hex value; it still renders. */
const COLORS = [
  { value: "primary", name: "Teal" },
  { value: "info", name: "Blue" },
  { value: "success", name: "Green" },
  { value: "warning", name: "Amber" },
  { value: "danger", name: "Red" },
  { value: "muted-foreground", name: "Grey" },
  { value: "foreground", name: "Charcoal" },
  { value: "primary-soft-foreground", name: "Deep orange" },
];

/** Names saved by earlier versions, mapped to today's tokens. */
const RENAMED: Record<string, string> = { "neutral-600": "muted-foreground", "neutral-800": "foreground", "accent-foreground": "primary-soft-foreground" };

function tone(color: string) {
  if (color.startsWith("#")) return { solid: color, tint: `${color}1f` };
  const token = RENAMED[color] ?? color;
  return { solid: `rgb(var(--${token}))`, tint: `rgb(var(--${token}) / 0.12)` };
}

const schema = z.object({
  name: z.string().min(1, "Name is required"),
  description: z.string().optional(),
  color: z.string(),
});
type FormValues = z.infer<typeof schema>;

function ListDialog({
  open,
  onOpenChange,
  list,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  list?: LeadList | null;
}) {
  const { create, update } = useLeadListMutations();
  const isEdit = !!list;
  const {
    register,
    handleSubmit,
    reset,
    setValue,
    watch,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { color: COLORS[0].value },
  });

  useEffect(() => {
    if (open)
      reset({
        name: list?.name ?? "",
        description: list?.description ?? "",
        color: list?.color ?? COLORS[0].value,
      });
  }, [open, list, reset]);

  const color = watch("color");

  const onSubmit = async (values: FormValues) => {
    try {
      if (isEdit && list) {
        await update.mutateAsync({ id: list.id, data: values });
        toast.success("List updated");
      } else {
        await create.mutateAsync(values);
        toast.success("List created");
      }
      onOpenChange(false);
    } catch {
      toast.error("Something went wrong");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit list" : "Create lead list"}</DialogTitle>
          <DialogDescription>
            Group leads into focused segments for targeted campaigns.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">List name</Label>
            <Input id="name" placeholder="List name" {...register("name")} />
            {errors.name && (
              <p className="text-xs text-danger">{errors.name.message}</p>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="description">Description</Label>
            <Textarea
              id="description"
              placeholder="What kind of leads belong here?"
              {...register("description")}
            />
          </div>
          <div className="space-y-2">
            <Label>Color</Label>
            <div className="flex flex-wrap gap-2">
              {COLORS.map((c) => (
                <button
                  key={c.value}
                  type="button"
                  onClick={() => setValue("color", c.value)}
                  className={cn(
                    "h-8 w-8 rounded-full ring-offset-2 ring-offset-background transition-shadow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    color === c.value && "ring-2 ring-foreground"
                  )}
                  style={{ backgroundColor: tone(c.value).solid }}
                  aria-label={`Colour: ${c.name}`}
                  aria-pressed={color === c.value}
                />
              ))}
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
             
              loading={create.isPending || update.isPending}
            >
              {isEdit ? "Save" : "Create list"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function LeadListsPage() {
  const navigate = useNavigate();
  const { data: lists, isLoading, error: loadError, refetch } = useLeadLists();
  const { remove } = useLeadListMutations();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editList, setEditList] = useState<LeadList | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<LeadList | null>(null);
  const [query, setQuery] = useState("");
  const [show, setShow] = useState<"all" | "with" | "empty">("all");
  const [sort, setSort] = useState<"newest" | "name" | "size">("newest");
  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const rows = (lists ?? []).filter((l) => (show === "all" || (show === "with" ? l.leadCount > 0 : l.leadCount === 0)) && (!needle || `${l.name} ${l.description ?? ""}`.toLowerCase().includes(needle)));
    if (sort === "name") rows.sort((a, b) => a.name.localeCompare(b.name));
    if (sort === "size") rows.sort((a, b) => b.leadCount - a.leadCount);
    return rows;
  }, [lists, query, show, sort]);
  const exportList = async (list: LeadList) => {
    try {
      const url = URL.createObjectURL(new Blob([await api.getText(`/lead-lists/${list.id}/export`)], { type: "text/csv" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `synex-list-${list.name.replace(/[^\w-]+/g, "-")}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("The list could not be exported. Try again.");
    }
  };

  const openCreate = () => {
    setEditList(null);
    setDialogOpen(true);
  };
  const openEdit = (list: LeadList) => {
    setEditList(list);
    setDialogOpen(true);
  };
  const handleDelete = async () => {
    if (!deleteTarget) return;
    await remove.mutateAsync(deleteTarget.id);
    toast.success("List deleted");
    setDeleteTarget(null);
  };

  if (loadError) return (
    <div role="alert" className="flex flex-wrap items-center gap-3 rounded-lg bg-danger-soft p-4 text-sm text-danger">
      <span>Lead lists could not be loaded. {loadError.message}</span>
      <Button size="sm" variant="secondary" onClick={() => refetch()}>Try again</Button>
    </div>
  );
  return (
    <div className="grid gap-6">
      <PageHeader
        title="Lead lists"
        description="Group leads so a campaign can reach the right people."
        actions={
          !isLoading && (!lists || lists.length === 0) ? undefined : (
          <Button onClick={openCreate}>
            <Plus className="h-4 w-4" />
            Create list
          </Button>
          )
        }
      />

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-40 w-full rounded-lg" />
          ))}
        </div>
      ) : !lists || lists.length === 0 ? (
        <EmptyState
          illustration="lists"
          title="No lead lists yet"
          description="Create your first list to start segmenting leads for campaigns."
          action={
            <Button onClick={openCreate}>
              <Plus className="h-4 w-4" />
              Create list
            </Button>
          }
        />
      ) : (
        <>
        <div role="search" aria-label="Find a list" className="flex flex-wrap items-end gap-3">
          <div className="grid min-w-0 flex-1 gap-1 sm:max-w-xs">
            <Label htmlFor="list-search">Search lists</Label>
            <div className="relative"><Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" /><Input id="list-search" className="pl-9" value={query} placeholder="Name or description" onChange={(e) => setQuery(e.target.value)} /></div>
          </div>
          <div className="grid gap-1"><Label htmlFor="list-show">Show</Label>
            <NativeSelect id="list-show" value={show} onChange={(e) => setShow(e.target.value as typeof show)}><option value="all">All lists</option><option value="with">With leads</option><option value="empty">Empty lists</option></NativeSelect></div>
          <div className="grid gap-1"><Label htmlFor="list-sort">Sort by</Label>
            <NativeSelect id="list-sort" value={sort} onChange={(e) => setSort(e.target.value as typeof sort)}><option value="newest">Newest first</option><option value="name">Name</option><option value="size">Most leads</option></NativeSelect></div>
          <p role="status" className="pb-2 text-sm text-muted-foreground">{shown.length} of {lists.length} {lists.length === 1 ? "list" : "lists"}</p>
        </div>
        {shown.length === 0 && <p className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">No list matches. Clear the search or choose All lists.</p>}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {shown.map((list) => (
            <Card
              key={list.id}
              className="group relative overflow-hidden transition-colors duration-150 hover:border-border-strong"
            >
              <div
                className="absolute inset-x-0 top-0 h-1"
                style={{ backgroundColor: tone(list.color).solid }}
              />
              <CardContent className="p-6">
                <div className="flex items-start justify-between">
                  <div
                    className="grid h-10 w-10 place-items-center rounded-lg"
                    style={{
                      backgroundColor: tone(list.color).tint,
                      color: tone(list.color).solid,
                    }}
                  >
                    <ListChecks className="h-5 w-5" />
                  </div>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${list.name}`}>
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onClick={() => openEdit(list)}>
                        <Pencil className="h-4 w-4" />
                        Edit
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        onClick={() => navigate(`/leads?listId=${list.id}`)}
                      >
                        <ArrowRight className="h-4 w-4" />
                        View leads
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => void exportList(list)}>
                        <Download className="h-4 w-4" />
                        Export CSV
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        destructive
                        onClick={() => setDeleteTarget(list)}
                      >
                        <Trash2 className="h-4 w-4" />
                        Delete
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
                <h3 className="mt-4 font-semibold">{list.name}</h3>
                <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
                  {list.description || "No description"}
                </p>
                <div className="mt-4 flex items-center justify-between">
                  <span className="text-sm font-medium">
                    {list.leadCount} {list.leadCount === 1 ? "lead" : "leads"}
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => navigate(`/leads?listId=${list.id}`)}
                  >
                    View
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
        </>
      )}

      <ListDialog open={dialogOpen} onOpenChange={setDialogOpen} list={editList} />
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        title="Delete list?"
        description={`"${deleteTarget?.name}" will be removed. Leads in this list won't be deleted.`}
        confirmLabel="Delete"
        destructive
        loading={remove.isPending}
        onConfirm={handleDelete}
      />
    </div>
  );
}
