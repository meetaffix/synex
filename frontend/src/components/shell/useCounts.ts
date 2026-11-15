import { useCampaignList } from "@/features/campaigns/hooks";
import { useConversationList } from "@/features/inbox/hooks";

/** The numbers beside sidebar items, from data the pages already load (so they cost no extra request). */
export function useNavCounts(): Record<string, number> {
  const conversations = useConversationList({ search: "", status: "all" });
  const campaigns = useCampaignList();
  return {
    "/inbox": conversations.data?.filter((conversation) => conversation.unread).length ?? 0,
    "/campaigns": campaigns.data?.filter((campaign) => campaign.status === "active").length ?? 0,
  };
}

/** What each count means, for assistive technology: "3 unread", "2 running". */
export const COUNT_MEANING: Record<string, string> = { "/inbox": "unread", "/campaigns": "running" };
