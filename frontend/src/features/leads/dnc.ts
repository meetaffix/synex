import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { api, ApiError } from "@/services/client";

export type DncKind = "person" | "company";

const pageSchema = z.object({
  items: z.array(z.object({ id: z.string(), kind: z.string(), name: z.string(), profileUrl: z.string().nullable(), source: z.string(), addedAt: z.string() })),
  total: z.number(),
});
const resultSchema = z.object({ added: z.number(), alreadyListed: z.number(), invalid: z.number() });
export type DncResult = z.infer<typeof resultSchema>;

function parse<S extends z.ZodType>(schema: S, data: unknown): z.infer<S> {
  const result = schema.safeParse(data);
  if (!result.success) throw new ApiError(0, "The server sent a response Synex could not read. Try again.");
  return result.data;
}

export const DNC_PAGE = 25;

export const dncService = {
  list: async (kind: DncKind, q: string, offset: number) =>
    parse(pageSchema, await api.get(`/do-not-contact?${new URLSearchParams({ kind, q, limit: String(DNC_PAGE), offset: String(offset) })}`)),
  add: async (kind: DncKind, text: string) => parse(resultSchema, await api.post("/do-not-contact", { kind, text })),
  importCsv: async (kind: DncKind, csv: string) => parse(resultSchema, await api.post("/do-not-contact/import", { kind, csv })),
  exportCsv: (kind: DncKind) => api.getText(`/do-not-contact/export?kind=${kind}`),
  remove: async (id: string) => {
    await api.delete(`/do-not-contact/${id}`);
  },
};

export const useDnc = (kind: DncKind, q: string, offset: number) => useQuery({ queryKey: ["dnc", kind, q, offset], queryFn: () => dncService.list(kind, q, offset) });

export function useDncActions() {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: ["dnc"] });
  return {
    add: useMutation({ mutationFn: ({ kind, text }: { kind: DncKind; text: string }) => dncService.add(kind, text), onSuccess: refresh }),
    importCsv: useMutation({ mutationFn: ({ kind, csv }: { kind: DncKind; csv: string }) => dncService.importCsv(kind, csv), onSuccess: refresh }),
    remove: useMutation({ mutationFn: dncService.remove, onSuccess: refresh }),
  };
}
