import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { api, ApiError } from "@/services/client";

/** An account's own connection list and received invitations, as Synex has read them (never live from LinkedIn). */
export type ConnectionKind = "connection" | "invitation";

const syncSchema = z.object({ status: z.string(), detail: z.string().nullable().optional(), lastSyncedAt: z.string().nullable().optional(), lastAdded: z.number().nullable().optional() });
const pageSchema = z.object({
  items: z.array(z.object({ id: z.string(), name: z.string(), headline: z.string(), location: z.string(), profileUrl: z.string(), source: z.string() })),
  total: z.number(),
  sync: syncSchema,
  note: z.string(),
});
const reloadSchema = z.object({ sync: syncSchema, note: z.string() });
const importSchema = z.object({ added: z.number(), alreadyStored: z.number(), duplicatesInFile: z.number(), invalid: z.number() });

export type ConnectionsPage = z.infer<typeof pageSchema>;
export type ImportResult = z.infer<typeof importSchema>;

function parse<S extends z.ZodType>(schema: S, data: unknown): z.infer<S> {
  const result = schema.safeParse(data);
  if (!result.success) throw new ApiError(0, "The server sent a response Synex could not read. Try again.");
  return result.data;
}

export const PAGE_SIZE = 25;
const base = (id: string) => `/linkedin-accounts/${id}/connections`;

export const connectionsService = {
  list: async (id: string, kind: ConnectionKind, q: string, offset: number): Promise<ConnectionsPage> =>
    parse(pageSchema, await api.get(`${base(id)}?${new URLSearchParams({ kind, q, limit: String(PAGE_SIZE), offset: String(offset) })}`)),
  reload: async (id: string, kind: ConnectionKind) => parse(reloadSchema, await api.post(`${base(id)}/reload`, { kind })),
  exportCsv: (id: string, kind: ConnectionKind) => api.getText(`${base(id)}/export?kind=${kind}`),
  importCsv: async (id: string, csv: string): Promise<ImportResult> => parse(importSchema, await api.post(`${base(id)}/import`, { csv })),
};

export const connectionKeys = { list: (id: string, kind: ConnectionKind, q: string, offset: number) => ["account-connections", id, kind, q, offset] as const, all: (id: string) => ["account-connections", id] as const };

export function useConnections(id: string, kind: ConnectionKind, q: string, offset: number) {
  return useQuery({
    queryKey: connectionKeys.list(id, kind, q, offset),
    queryFn: () => connectionsService.list(id, kind, q, offset),
    // While a read is queued or running, look again every few seconds so the list fills in by itself.
    refetchInterval: (query) => (["queued", "running"].includes(query.state.data?.sync.status ?? "") ? 5000 : false),
  });
}

export function useConnectionActions(id: string) {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: connectionKeys.all(id) });
  return {
    reload: useMutation({ mutationFn: (kind: ConnectionKind) => connectionsService.reload(id, kind), onSuccess: refresh }),
    importCsv: useMutation({ mutationFn: (csv: string) => connectionsService.importCsv(id, csv), onSuccess: refresh }),
  };
}
