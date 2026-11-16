import { z } from "zod";
import { api, ApiError } from "@/services/client";

const statsSchema = z.object({
  totalLeads: z.number(),
  invitesSent: z.number(),
  connected: z.number(),
  replied: z.number(),
  interested: z.number(),
  messagesSent: z.number(),
  acceptanceRate: z.number(),
  replyRate: z.number(),
});

export const campaignSchema = z.object({
  id: z.string(),
  name: z.string(),
  status: z.string(),
  displayStatus: z.string().default("draft"),
  accountId: z.string().nullable(),
  accountIds: z.array(z.string()),
  accountName: z.string(),
  leadListName: z.string(),
  stats: statsSchema,
});

export type Campaign = z.infer<typeof campaignSchema>;

export const campaignsService = {
  list: async (): Promise<Campaign[]> => {
    const result = z.array(campaignSchema).safeParse(await api.get("/campaigns"));
    if (!result.success) throw new ApiError(0, "The server sent a response Synex could not read. Try again.");
    return result.data;
  },
};

/** Every sender account a campaign can send from: its primary account plus its pool. */
export const campaignAccountIds = (campaign: Campaign): string[] =>
  [...new Set([campaign.accountId, ...campaign.accountIds].filter((id): id is string => !!id))];
