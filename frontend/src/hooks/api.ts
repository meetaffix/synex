import {
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import {
  dashboardService,
  leadsService,
  leadListsService,
  campaignsService,
  conversationsService,
  templatesService,
  analyticsService,
  settingsService,
  teamService,
  type LeadFilters,
  type ConversationFilters,
  type AppSettings,
  type TeamRole,
} from "@/services/resources";
import type {
  Lead,
  LeadList,
  Campaign,
  Template,
  Conversation,
  LeadStatus,
} from "@/types";

export const qk = {
  dashboard: ["dashboard"] as const,
  leads: (f?: LeadFilters) => ["leads", f ?? {}] as const,
  leadLists: ["lead-lists"] as const,
  campaigns: ["campaigns"] as const,
  campaign: (id: string) => ["campaigns", id] as const,
  conversations: (f?: ConversationFilters) => ["conversations", f ?? {}] as const,
  messages: (id: string) => ["messages", id] as const,
  templates: ["templates"] as const,
  analytics: ["analytics", "overview"] as const,
};

/* ----------------------------- Dashboard ------------------------------ */
// Both hooks share one `/dashboard` request (same queryKey) and slice it,
// so stats + activity render from a single round-trip.
export const useDashboardStats = () =>
  useQuery({
    queryKey: qk.dashboard,
    queryFn: dashboardService.get,
    select: (d) => d.stats,
  });
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

/* ----------------------------- Campaigns ------------------------------ */
export const useCampaigns = () =>
  useQuery({ queryKey: qk.campaigns, queryFn: campaignsService.list });
export const useCampaign = (id: string) =>
  useQuery({
    queryKey: qk.campaign(id),
    queryFn: () => campaignsService.get(id),
    enabled: !!id,
  });

export function useCampaignMutations() {
  const qc = useQueryClient();
  const invalidate = (id?: string) => {
    qc.invalidateQueries({ queryKey: qk.campaigns });
    if (id) qc.invalidateQueries({ queryKey: qk.campaign(id) });
    qc.invalidateQueries({ queryKey: qk.dashboard });
  };
  return {
    create: useMutation({
      mutationFn: (data: Partial<Campaign>) => campaignsService.create(data),
      onSuccess: () => invalidate(),
    }),
    update: useMutation({
      mutationFn: ({ id, data }: { id: string; data: Partial<Campaign> }) =>
        campaignsService.update(id, data),
      onSuccess: (_d, v) => invalidate(v.id),
    }),
    remove: useMutation({
      mutationFn: (id: string) => campaignsService.remove(id),
      onSuccess: () => invalidate(),
    }),
  };
}

/** Live execution view — polls faster while the campaign is running. */
export const useCampaignMonitor = (id: string, active: boolean) =>
  useQuery({
    queryKey: ["campaigns", id, "monitor"] as const,
    queryFn: () => campaignsService.monitor(id),
    enabled: !!id,
    refetchInterval: active ? 10_000 : 60_000,
  });

export function useRunRecovery(campaignId: string) {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["campaigns", campaignId, "monitor"] });
    qc.invalidateQueries({ queryKey: qk.campaign(campaignId) });
  };
  return {
    retry: useMutation({
      mutationFn: (runId: string) => campaignsService.retryRun(campaignId, runId),
      onSuccess: invalidate,
    }),
    skip: useMutation({
      mutationFn: (runId: string) => campaignsService.skipRunStep(campaignId, runId),
      onSuccess: invalidate,
    }),
  };
}

/* -------------------------------- Team --------------------------------- */
// Both hooks share one `/team` request (same queryKey) and slice it.
export const useTeamSeat = () =>
  useQuery({ queryKey: ["team"], queryFn: teamService.get, select: (d) => d.seat });
export const useTeamMembers = () =>
  useQuery({ queryKey: ["team"], queryFn: teamService.get, select: (d) => d.members });

export function useTeamMutations() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["team"] });
  return {
    invite: useMutation({
      mutationFn: ({ email, role }: { email: string; role: TeamRole }) =>
        teamService.invite(email, role),
      onSuccess: invalidate,
    }),
    updateRole: useMutation({
      mutationFn: ({ id, role }: { id: string; role: TeamRole }) =>
        teamService.updateRole(id, role),
      onSuccess: invalidate,
    }),
    remove: useMutation({
      mutationFn: (id: string) => teamService.remove(id),
      onSuccess: invalidate,
    }),
  };
}

/* --------------------------- Conversations ---------------------------- */
// The extension syncs LinkedIn threads every minute — keep the inbox fresh.
export const useConversations = (filters?: ConversationFilters) =>
  useQuery({
    queryKey: qk.conversations(filters),
    queryFn: () => conversationsService.list(filters),
    refetchInterval: 15_000,
  });

export const useMessages = (id: string) =>
  useQuery({
    queryKey: qk.messages(id),
    queryFn: () => conversationsService.messages(id),
    enabled: !!id,
    refetchInterval: 10_000,
  });

export function useConversationMutations() {
  const qc = useQueryClient();
  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: ["conversations"] });
  };
  return {
    send: useMutation({
      mutationFn: ({ id, body }: { id: string; body: string }) =>
        conversationsService.sendMessage(id, body),
      onSuccess: (_d, v) => {
        qc.invalidateQueries({ queryKey: qk.messages(v.id) });
        invalidateAll();
      },
    }),
    compose: useMutation({
      mutationFn: ({ leadId, body }: { leadId: string; body: string }) =>
        conversationsService.compose(leadId, body),
      onSuccess: (res) => {
        qc.invalidateQueries({ queryKey: qk.messages(res.conversation.id) });
        invalidateAll();
      },
    }),
    update: useMutation({
      mutationFn: ({ id, data }: { id: string; data: Partial<Conversation> }) =>
        conversationsService.update(id, data),
      onSuccess: invalidateAll,
    }),
  };
}

export function useUnreadCount() {
  const { data } = useConversations();
  return data?.filter((c) => c.unread).length ?? 0;
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

/* ----------------------------- Analytics ------------------------------ */
export const useAnalyticsOverview = () =>
  useQuery({ queryKey: qk.analytics, queryFn: analyticsService.overview });

/* ------------------------------ Settings ------------------------------ */
export const useSettings = () =>
  useQuery({ queryKey: ["settings"], queryFn: settingsService.get });

export function useSettingsMutations() {
  const qc = useQueryClient();
  const set = (data: AppSettings) => qc.setQueryData(["settings"], data);
  return {
    notifications: useMutation({
      mutationFn: (prefs: Record<string, boolean>) =>
        settingsService.updateNotifications(prefs),
      onSuccess: set,
    }),
    twoFactor: useMutation({
      mutationFn: (enabled: boolean) => settingsService.updateTwoFactor(enabled),
      onSuccess: set,
    }),
    integration: useMutation({
      mutationFn: ({
        provider,
        connected,
        config,
      }: {
        provider: string;
        connected: boolean;
        config?: Record<string, unknown>;
      }) => settingsService.updateIntegration(provider, connected, config),
      onSuccess: set,
    }),
    changePassword: useMutation({
      mutationFn: ({
        currentPassword,
        newPassword,
      }: {
        currentPassword: string;
        newPassword: string;
      }) => settingsService.changePassword(currentPassword, newPassword),
    }),
  };
}
