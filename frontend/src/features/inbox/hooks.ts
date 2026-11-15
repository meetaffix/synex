import { useQuery } from "@tanstack/react-query";
import { inboxService, type InboxFilters } from "./service";

export const useConversationList = (filters: InboxFilters) =>
  useQuery({ queryKey: ["inbox", "list", filters], queryFn: () => inboxService.list(filters) });

export const useThread = (conversationId: string | null) =>
  useQuery({
    queryKey: ["inbox", "thread", conversationId],
    queryFn: () => inboxService.thread(conversationId as string),
    enabled: conversationId !== null,
  });
