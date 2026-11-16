import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Plus,
  FileText,
  MoreHorizontal,
  Pencil,
  Copy,
  Trash2,
  TrendingUp,
} from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { EmptyState } from "@/components/shared/EmptyState";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { MessageEditor } from "@/features/campaigns/components/sequence/MessageEditor";
import { useTemplates, useTemplateMutations } from "@/hooks/api";
import { toast } from "@/components/ui/sonner";
import { formatPercent } from "@/utils/format";
import type { Template, TemplateCategory } from "@/types";

const CATEGORIES: { value: TemplateCategory; label: string }[] = [
  { value: "connection", label: "Connection" },
  { value: "first_message", label: "First message" },
  { value: "follow_up", label: "Follow-up" },
  { value: "reply", label: "Reply" },
];

const CATEGORY_VARIANT: Record<
  TemplateCategory,
  "default" | "secondary" | "success" | "warning"
> = {
  connection: "default",
  first_message: "secondary",
  follow_up: "warning",
  reply: "success",
};

const schema = z.object({
  name: z.string().min(1, "Name is required"),
  category: z.string(),
  body: z.string().min(1, "Message body is required"),
  shortcut: z.string().optional(),
});
type FormValues = z.infer<typeof schema>;

function TemplateDialog({
  open,
  onOpenChange,
  template,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  template?: Template | null;
}) {
  const { create, update } = useTemplateMutations();
  const isEdit = !!template;
  const {
    register,
    handleSubmit,
    reset,
    setValue,
    watch,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { category: "first_message", body: "" },
  });

  useEffect(() => {
    if (open)
      reset({
        name: template?.name ?? "",
        category: template?.category ?? "first_message",
        body: template?.body ?? "",
        shortcut: template?.shortcut ?? "",
      });
  }, [open, template, reset]);

  const onSubmit = async (values: FormValues) => {
    try {
      if (isEdit && template) {
        await update.mutateAsync({ id: template.id, data: values as Partial<Template> });
        toast.success("Template updated");
      } else {
        await create.mutateAsync(values as Partial<Template>);
        toast.success("Template created");
      }
      onOpenChange(false);
    } catch (error) {
      toast.error(error instanceof Error && error.message ? error.message : "Something went wrong");
    }
  };

  const category = watch("category");
  const body = watch("body");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit template" : "New template"}</DialogTitle>
          <DialogDescription>
            Save reusable messages with personalization variables.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="name">Template name</Label>
              <Input id="name" {...register("name")} />
              {errors.name && (
                <p className="text-xs text-danger">{errors.name.message}</p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label>Category</Label>
              <Select
                value={category}
                onValueChange={(v) => setValue("category", v)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CATEGORIES.map((c) => (
                    <SelectItem key={c.value} value={c.value}>
                      {c.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="shortcut">Shortcut (optional)</Label>
            <Input id="shortcut" placeholder="thanks" {...register("shortcut")} />
            <p className="text-xs text-muted-foreground">Type / and the shortcut in the inbox reply box to insert this text, for example /thanks.</p>
          </div>
          <div className="space-y-1.5">
            <Label>Message</Label>
            <MessageEditor
              value={body}
              onChange={(v) => setValue("body", v, { shouldValidate: true })}
              aiStepType={
                category === "connection"
                  ? "connection_request"
                  : category === "follow_up"
                    ? "follow_up"
                    : "message"
              }
            />
            {errors.body && (
              <p className="text-xs text-danger">{errors.body.message}</p>
            )}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
             
              loading={create.isPending || update.isPending}
            >
              {isEdit ? "Save" : "Create template"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function TemplatesPage() {
  const { data: templates, isLoading, error: loadError, refetch } = useTemplates();
  const { create, remove } = useTemplateMutations();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editTemplate, setEditTemplate] = useState<Template | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Template | null>(null);

  const openCreate = () => {
    setEditTemplate(null);
    setDialogOpen(true);
  };

  const clone = async (t: Template) => {
    await create.mutateAsync({
      name: `${t.name} (copy)`,
      category: t.category,
      body: t.body,
    });
    toast.success("Template cloned");
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    await remove.mutateAsync(deleteTarget.id);
    toast.success("Template deleted");
    setDeleteTarget(null);
  };

  if (loadError) return (
    <div role="alert" className="flex flex-wrap items-center gap-3 rounded-lg bg-danger-soft p-4 text-sm text-danger">
      <span>Templates could not be loaded. {loadError.message}</span>
      <Button size="sm" variant="secondary" onClick={() => refetch()}>Try again</Button>
    </div>
  );
  return (
    <div className="grid gap-6">
      <PageHeader
        title="Templates"
        description="Reusable messages for connection requests, introductions and follow-ups."
        actions={
          !isLoading && (!templates || templates.length === 0) ? undefined : (
          <Button onClick={openCreate}>
            <Plus className="h-4 w-4" />
            New template
          </Button>
          )
        }
      />

      {isLoading ? (
        <div className="grid gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-48 rounded-lg" />
          ))}
        </div>
      ) : !templates || templates.length === 0 ? (
        <EmptyState
          illustration="templates"
          title="No templates yet"
          description="Keep reusable drafts for manual follow-ups."
          action={
            <Button onClick={openCreate}>
              <Plus className="h-4 w-4" />
              New template
            </Button>
          }
        />
      ) : (
        <div className="grid gap-3">
          {templates.map((t) => (
            <Card key={t.id} className="group flex flex-col transition-transform duration-200 hover:-translate-y-0.5">
              <CardContent className="flex flex-1 flex-col p-6">
                <div className="flex items-start justify-between">
                  <Badge variant={CATEGORY_VARIANT[t.category]}>
                    {CATEGORIES.find((c) => c.value === t.category)?.label}
                  </Badge>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${t.name}`}>
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem
                        onClick={() => {
                          setEditTemplate(t);
                          setDialogOpen(true);
                        }}
                      >
                        <Pencil className="h-4 w-4" />
                        Edit
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => clone(t)}>
                        <Copy className="h-4 w-4" />
                        Clone
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        destructive
                        onClick={() => setDeleteTarget(t)}
                      >
                        <Trash2 className="h-4 w-4" />
                        Delete
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
                <h3 className="mt-3 font-semibold">{t.name}{t.shortcut ? <span className="ml-2 rounded bg-surface-muted px-1.5 py-0.5 text-xs font-normal text-muted-foreground">/{t.shortcut}</span> : null}</h3>
                <p className="mt-2 line-clamp-4 flex-1 text-sm text-muted-foreground">
                  {t.body}
                </p>
                <div className="mt-4 flex items-center gap-3 border-t border-border pt-3">
                  <Button variant="outline" size="sm" onClick={async()=>{try{await navigator.clipboard.writeText(t.body);toast.success("Template copied");}catch{toast.error("Select and copy the template text.");}}}>Copy text</Button>
                  <span className="text-xs text-muted-foreground">Manual draft</span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <TemplateDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        template={editTemplate}
      />
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        title="Delete template?"
        description={`"${deleteTarget?.name}" will be permanently removed.`}
        confirmLabel="Delete"
        destructive
        loading={remove.isPending}
        onConfirm={handleDelete}
      />
    </div>
  );
}
