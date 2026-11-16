import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/services/client";
import { requestFailureMessage } from "@/features/linkedin-accounts/copy";

const listsSchema = z.array(z.object({ id: z.string(), name: z.string(), count: z.number(), createdAt: z.string() }));
const detailSchema = z.object({
  id: z.string(),
  name: z.string(),
  total: z.number(),
  items: z.array(z.object({ id: z.string(), name: z.string(), url: z.string(), industry: z.string().nullable(), location: z.string().nullable() })),
});
const resultSchema = z.object({ added: z.number(), alreadyListed: z.number(), invalid: z.number() });

function read<S extends z.ZodType>(schema: S, data: unknown): z.infer<S> {
  const result = schema.safeParse(data);
  if (!result.success) throw new ApiError(0, "The server sent a response Synex could not read. Try again.");
  return result.data;
}

/** Companies collected from company searches and Sales Navigator accounts. They are never messaged. */
export function CompanyListsPage() {
  const qc = useQueryClient();
  const lists = useQuery({ queryKey: ["company-lists"], queryFn: async () => read(listsSchema, await api.get("/company-lists")) });
  const [openId, setOpenId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<{ id: string; name: string } | null>(null);
  const detail = useQuery({ queryKey: ["company-list", openId], enabled: !!openId, queryFn: async () => read(detailSchema, await api.get(`/company-lists/${openId}`)) });
  const block = useMutation({ mutationFn: async (id: string) => read(resultSchema, await api.post(`/company-lists/${id}/do-not-contact`)) });
  const remove = useMutation({
    mutationFn: (id: string) => api.delete(`/company-lists/${id}`),
    onSuccess: () => {
      setOpenId(null);
      return qc.invalidateQueries({ queryKey: ["company-lists"] });
    },
  });

  return (
    <div className="grid grid-cols-1 gap-4">
      <p className="text-sm text-muted-foreground">
        Lists of companies made from LinkedIn company searches or Sales Navigator accounts. Nothing is sent to a company. You can put a whole list on the do-not-contact list.
      </p>
      {lists.isLoading && <Skeleton className="h-24 w-full" />}
      {lists.isError && <p role="alert" className="text-sm text-danger">{requestFailureMessage(lists.error)}</p>}
      {lists.data?.length === 0 && (
        <p className="rounded-lg border border-border p-4 text-sm text-muted-foreground">
          No company lists yet. Use Add leads, then LinkedIn companies or Sales Navigator accounts.
        </p>
      )}
      <ul aria-label="Company lists" className="grid gap-3">
        {lists.data?.map((item) => (
          <li key={item.id} className="grid gap-3 rounded-lg border border-border bg-surface p-4">
            <div className="flex flex-wrap items-center gap-3">
              <h2 className="min-w-0 flex-1 truncate text-base font-semibold">{item.name}</h2>
              <span className="text-sm text-muted-foreground">{item.count} companies</span>
              <Button size="sm" variant="outline" aria-expanded={openId === item.id} onClick={() => setOpenId(openId === item.id ? null : item.id)}>
                {openId === item.id ? "Hide" : "View"}
              </Button>
              <Button size="sm" variant="outline" loading={block.isPending && block.variables === item.id}
                onClick={() => block.mutate(item.id, { onSuccess: (r) => toast.success(`${r.added} added to do-not-contact, ${r.alreadyListed} already listed.`), onError: (e) => toast.error(requestFailureMessage(e)) })}>
                Add all to do-not-contact
              </Button>
              <Button size="sm" variant="ghost" className="text-danger" onClick={() => setDeleting({ id: item.id, name: item.name })}>Delete</Button>
            </div>
            {openId === item.id && (
              <div role="region" tabIndex={0} aria-label={`${item.name} (scrolls sideways)`} className="overflow-x-auto rounded-lg border border-border">
                {detail.isLoading && <Skeleton className="h-16 w-full" />}
                {detail.data && (
                  <table className="w-full min-w-[30rem] text-sm">
                    <caption className="sr-only">Companies in {item.name}</caption>
                    <thead className="bg-surface-muted text-left text-xs text-muted-foreground">
                      <tr>
                        <th scope="col" className="px-3 py-2 font-medium">Company</th>
                        <th scope="col" className="px-3 py-2 font-medium">Industry</th>
                        <th scope="col" className="px-3 py-2 font-medium">Location</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.data.items.map((row) => (
                        <tr key={row.id} className="border-t border-border">
                          <th scope="row" className="px-3 py-2 text-left font-medium"><a className="underline-offset-2 hover:underline" href={row.url} target="_blank" rel="noreferrer noopener">{row.name}</a></th>
                          <td className="px-3 py-2">{row.industry}</td>
                          <td className="px-3 py-2">{row.location}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete ${deleting?.name ?? "this list"}?`}
        description="The list and its companies are removed. Nothing on LinkedIn changes."
        confirmLabel="Delete list"
        destructive
        loading={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting.id, { onSuccess: () => { toast.success("List deleted."); setDeleting(null); }, onError: (e) => toast.error(requestFailureMessage(e)) })}
      />
    </div>
  );
}
