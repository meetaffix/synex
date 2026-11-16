import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useLeadMutations, useLeadLists } from "@/hooks/api";
import { toast } from "@/components/ui/sonner";
import type { Lead, LeadStatus } from "@/types";

const TIME_ZONES = Intl.supportedValuesOf("timeZone");
/** Names Synex already fills in; a custom variable may not reuse them. */
const RESERVED = ["first_name", "last_name", "name", "full_name", "company", "job_title", "designation", "location", "headline", "industry"];
const variableProblem = (name: string, names: string[]) =>
  !/^[A-Za-z][A-Za-z0-9_]{0,39}$/.test(name)
    ? "Use letters, digits and underscores, starting with a letter."
    : RESERVED.includes(name.toLowerCase()) || /^(linkedin|sender)_/i.test(name)
      ? "Synex already fills this one in. Choose another name."
      : names.filter((n) => n === name).length > 1
        ? "Each variable needs its own name."
        : null;

const schema = z.object({
  firstName: z.string().min(1, "Required"),
  lastName: z.string().min(1, "Required"),
  company: z.string().optional(),
  jobTitle: z.string().optional(),
  linkedinUrl: z
    .string()
    .url("Enter a valid URL")
    .optional()
    .or(z.literal("")),
  email: z.string().email("Invalid email").optional().or(z.literal("")),
  location: z.string().optional(),
  timezone: z
    .string()
    .optional()
    .refine((value) => !value || TIME_ZONES.includes(value), "Pick a time zone from the list, such as Europe/Paris."),
  status: z.string(),
  listId: z.string().optional(),
  notes: z.string().optional(),
});
type FormValues = z.infer<typeof schema>;

const STATUS_OPTIONS: LeadStatus[] = [
  "new",
  "contacted",
  "connected",
  "replied",
  "interested",
  "not_interested",
  "bounced",
];

interface LeadFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  lead?: Lead | null;
}

export function LeadFormDialog({ open, onOpenChange, lead }: LeadFormDialogProps) {
  const { create, update } = useLeadMutations();
  const { data: lists } = useLeadLists();
  const isEdit = !!lead;
  const [vars, setVars] = useState<{ name: string; value: string }[]>([]);

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    watch,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { status: "new" },
  });

  useEffect(() => {
    if (open) {
      reset({
        firstName: lead?.firstName ?? "",
        lastName: lead?.lastName ?? "",
        company: lead?.company ?? "",
        jobTitle: lead?.jobTitle ?? "",
        linkedinUrl: lead?.linkedinUrl ?? "",
        email: lead?.email ?? "",
        location: lead?.location ?? "",
        timezone: lead?.timezone ?? "",
        status: lead?.status ?? "new",
        listId: lead?.listIds?.[0] ?? "none",
        notes: lead?.notes ?? "",
      });
      setVars(Object.entries(lead?.variables ?? {}).map(([name, value]) => ({ name, value })));
    }
  }, [open, lead, reset]);

  const names = vars.map((v) => v.name);
  const problems = vars.map((v) => variableProblem(v.name, names));
  const onSubmit = async (values: FormValues) => {
    if (problems.some(Boolean)) return;
    const payload: Partial<Lead> = {
      firstName: values.firstName,
      lastName: values.lastName,
      company: values.company ?? "",
      jobTitle: values.jobTitle ?? "",
      linkedinUrl: values.linkedinUrl ?? "",
      email: values.email || null,
      location: values.location || null,
      timezone: values.timezone || null,
      status: values.status as LeadStatus,
      notes: values.notes || null,
      variables: Object.fromEntries(vars.filter((v) => v.name).map((v) => [v.name, v.value])),
      listIds:
        values.listId && values.listId !== "none" ? [values.listId] : [],
    };
    try {
      if (isEdit && lead) {
        await update.mutateAsync({ id: lead.id, data: payload });
        toast.success("Lead updated");
      } else {
        await create.mutateAsync(payload);
        toast.success("Lead created");
      }
      onOpenChange(false);
    } catch {
      toast.error("Something went wrong");
    }
  };

  const status = watch("status");
  const listId = watch("listId");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit lead" : "Add new lead"}</DialogTitle>
          <DialogDescription>
            {isEdit
              ? "Update this lead's information."
              : "Manually add a lead to your workspace."}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="firstName">First name</Label>
              <Input id="firstName" {...register("firstName")} />
              {errors.firstName && (
                <p className="text-xs text-danger">
                  {errors.firstName.message}
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="lastName">Last name</Label>
              <Input id="lastName" {...register("lastName")} />
              {errors.lastName && (
                <p className="text-xs text-danger">
                  {errors.lastName.message}
                </p>
              )}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="company">Company</Label>
              <Input id="company" {...register("company")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="jobTitle">Job title</Label>
              <Input id="jobTitle" {...register("jobTitle")} />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="linkedinUrl">LinkedIn URL</Label>
            <Input
              id="linkedinUrl"
              placeholder="https://linkedin.com/in/…"
              {...register("linkedinUrl")}
            />
            {errors.linkedinUrl && (
              <p className="text-xs text-danger">
                {errors.linkedinUrl.message}
              </p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" {...register("email")} />
              {errors.email && (
                <p className="text-xs text-danger">{errors.email.message}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="location">Location</Label>
              <Input id="location" {...register("location")} />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="timezone">Time zone</Label>
            <Input
              id="timezone"
              list="lead-time-zones"
              autoComplete="off"
              aria-invalid={!!errors.timezone}
              aria-describedby="timezone-help"
              {...register("timezone")}
            />
            <datalist id="lead-time-zones">
              {TIME_ZONES.map((zone) => (
                <option key={zone} value={zone} />
              ))}
            </datalist>
            <p id="timezone-help" className={errors.timezone ? "text-xs text-danger" : "text-xs text-muted-foreground"}>
              {errors.timezone?.message ?? "Working hours for this lead use this time zone. Leave blank to use the campaign's."}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Status</Label>
              <Select
                value={status}
                onValueChange={(v) => setValue("status", v)}
              >
                <SelectTrigger aria-label="Status">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {STATUS_OPTIONS.map((opt) => (
                    <SelectItem key={opt} value={opt}>
                      {opt.replace("_", " ")}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Lead list</Label>
              <Select
                value={listId}
                onValueChange={(v) => setValue("listId", v)}
              >
                <SelectTrigger aria-label="Lead list">
                  <SelectValue placeholder="Assign to a list" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">No list</SelectItem>
                  {lists?.map((l) => (
                    <SelectItem key={l.id} value={l.id}>
                      {l.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Campaign variables</legend>
            <p className="text-xs text-muted-foreground">
              Extra facts for this person, such as an event you both attended. Use one in a message as {"{{name}}"}, for example {"{{eventName}}"}.
            </p>
            {vars.map((v, index) => (
              <div key={index} className="grid gap-1">
                <div className="grid grid-cols-[1fr_1fr_auto] items-center gap-2">
                  <Input aria-label={`Variable ${index + 1} name`} placeholder="eventName" value={v.name} aria-invalid={!!problems[index]}
                    onChange={(e) => setVars(vars.map((x, i) => (i === index ? { ...x, name: e.target.value } : x)))} />
                  <Input aria-label={`Variable ${index + 1} value`} placeholder="SaaStr 2026" value={v.value}
                    onChange={(e) => setVars(vars.map((x, i) => (i === index ? { ...x, value: e.target.value } : x)))} />
                  <Button type="button" variant="ghost" size="sm" aria-label={`Remove variable ${index + 1}`} onClick={() => setVars(vars.filter((_, i) => i !== index))}>Remove</Button>
                </div>
                {problems[index] && <p className="text-xs text-danger">{problems[index]}</p>}
              </div>
            ))}
            {vars.length < 20 && <Button type="button" variant="outline" size="sm" onClick={() => setVars([...vars, { name: "", value: "" }])}>New variable</Button>}
          </fieldset>

          <div className="space-y-2">
            <Label htmlFor="notes">Notes</Label>
            <Textarea
              id="notes"
              placeholder="Add context, intro details, or reminders…"
              {...register("notes")}
            />
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
             
              loading={create.isPending || update.isPending}
            >
              {isEdit ? "Save changes" : "Add lead"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
