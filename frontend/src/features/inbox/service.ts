import { z } from "zod";
import { api, ApiError } from "@/services/client";

export const conversationStatusSchema = z.enum(["active", "interested", "not_interested", "archived"]);

export const conversationSchema = z.object({
  id: z.string(),
  leadName: z.string(),
  leadTitle: z.string().nullable().optional(),
  leadCompany: z.string().nullable().optional(),
  campaignName: z.string().nullable().optional(),
  lastMessagePreview: z.string().nullable().optional(),
  lastMessageAt: z.string(),
  unread: z.boolean(),
  status: conversationStatusSchema,
});

export const messageSchema = z.object({
  id: z.string(),
  direction: z.enum(["inbound", "outbound"]),
  body: z.string(),
  sentAt: z.string(),
  deliveryStatus: z.enum(["queued", "sent", "failed"]).optional(),
  deliveryError: z.string().nullable().optional(),
});

export type Conversation = z.infer<typeof conversationSchema>;
export type ConversationStatus = z.infer<typeof conversationStatusSchema>;
export type ThreadMessage = z.infer<typeof messageSchema>;

export interface InboxFilters {
  search: string;
  status: ConversationStatus | "all";
}

function parse<T>(schema: z.ZodType<T>, data: unknown): T {
  const result = schema.safeParse(data);
  if (!result.success) throw new ApiError(0, "The server sent a response Synex could not read. Try again.");
  return result.data;
}

export const inboxService = {
  list: async (filters: InboxFilters): Promise<Conversation[]> => {
    const params = new URLSearchParams();
    if (filters.status !== "all") params.set("status", filters.status);
    if (filters.search.trim()) params.set("search", filters.search.trim());
    const query = params.toString();
    return parse(z.array(conversationSchema), await api.get(`/conversations${query ? `?${query}` : ""}`));
  },

  /** Reading a thread also marks it read on the server. */
  thread: async (conversationId: string): Promise<ThreadMessage[]> =>
    parse(z.array(messageSchema), await api.get(`/conversations?conversationId=${encodeURIComponent(conversationId)}`)),
};
