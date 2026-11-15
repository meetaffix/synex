import { useEffect, useState } from "react";
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
  { value: "primary-soft-foreground", name: "Deep teal" },
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
                    "h-8 w-8 rounded-full ring-offset-2 ring-offset-background transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
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
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {lists.map((list) => (
            <Card
              key={list.id}
              className="group relative overflow-hidden transition-transform duration-200 hover:-translate-y-0.5"
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
