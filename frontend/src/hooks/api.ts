import {
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import {
  dashboardService,
  leadsService,
  leadListsService,
  templatesService,
  type LeadFilters,
} from "@/services/resources";
import type { Lead, LeadList, Template, LeadStatus } from "@/types";

export const qk = {
  dashboard: ["dashboard"] as const,
  leads: (f?: LeadFilters) => ["leads", f ?? {}] as const,
  leadLists: ["lead-lists"] as const,
  templates: ["templates"] as const,
};

// Reads the activity slice of the shared `/dashboard` request.
export const useActivity = () =>
  useQuery({
    queryKey: qk.dashboard,
    queryFn: dashboardService.get,
    select: (d) => d.activity,
  });

/* ------------------------------- Leads -------------------------------- */
export const useLeads = (filters?: LeadFilters) =>
  useQuery({
    queryKey: qk.leads(filters),
    queryFn: () => leadsService.list(filters),
  });

export function useLeadMutations() {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["leads"] });
    qc.invalidateQueries({ queryKey: qk.leadLists });
    qc.invalidateQueries({ queryKey: qk.dashboard });
  };
  return {
    create: useMutation({
      mutationFn: (data: Partial<Lead>) => leadsService.create(data),
      onSuccess: invalidate,
    }),
    update: useMutation({
      mutationFn: ({ id, data }: { id: string; data: Partial<Lead> }) =>
        leadsService.update(id, data),
      onSuccess: invalidate,
    }),
    remove: useMutation({
      mutationFn: (id: string) => leadsService.remove(id),
      onSuccess: invalidate,
    }),
    bulkImport: useMutation({
      mutationFn: ({ leads, listIds }: { leads: Partial<Lead>[]; listIds: string[] }) =>
        leadsService.bulkImport(leads, listIds),
      onSuccess: invalidate,
    }),
    bulkDelete: useMutation({
      mutationFn: (ids: string[]) => leadsService.bulkDelete(ids),
      onSuccess: invalidate,
    }),
    deleteAll: useMutation({
      mutationFn: (filters?: LeadFilters) => leadsService.deleteAll(filters),
      onSuccess: invalidate,
    }),
    bulkStatus: useMutation({
      mutationFn: ({ ids, status }: { ids: string[]; status: LeadStatus }) =>
        leadsService.bulkStatus(ids, status),
      onSuccess: invalidate,
    }),
  };
}

/** Poll import jobs while any are running so progress updates live. */
export const useImportJobs = (enabled = true) =>
  useQuery({
    queryKey: ["import-jobs"],
    queryFn: leadsService.importJobs,
    enabled,
    refetchInterval: (query) => {
      const jobs = query.state.data;
      const active = jobs?.some(
        (j) => j.status === "pending" || j.status === "processing"
      );
      return active ? 2_000 : 10_000;
    },
  });

/* ----------------------------- Lead lists ----------------------------- */
export const useLeadLists = () =>
  useQuery({ queryKey: qk.leadLists, queryFn: leadListsService.list });

export function useLeadListMutations() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: qk.leadLists });
  return {
    create: useMutation({
      mutationFn: (data: Partial<LeadList>) => leadListsService.create(data),
      onSuccess: invalidate,
    }),
    update: useMutation({
      mutationFn: ({ id, data }: { id: string; data: Partial<LeadList> }) =>
        leadListsService.update(id, data),
      onSuccess: invalidate,
    }),
    remove: useMutation({
      mutationFn: (id: string) => leadListsService.remove(id),
      onSuccess: () => {
        invalidate();
        qc.invalidateQueries({ queryKey: ["leads"] });
      },
    }),
  };
}

/* ----------------------------- Templates ------------------------------ */
export const useTemplates = () =>
  useQuery({ queryKey: qk.templates, queryFn: templatesService.list });

export function useTemplateMutations() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: qk.templates });
  return {
    create: useMutation({
      mutationFn: (data: Partial<Template>) => templatesService.create(data),
      onSuccess: invalidate,
    }),
    update: useMutation({
      mutationFn: ({ id, data }: { id: string; data: Partial<Template> }) =>
        templatesService.update(id, data),
      onSuccess: invalidate,
    }),
    remove: useMutation({
      mutationFn: (id: string) => templatesService.remove(id),
      onSuccess: invalidate,
    }),
  };
}
