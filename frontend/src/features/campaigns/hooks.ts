import { useQuery } from "@tanstack/react-query";
import { campaignsService } from "./service";

export const useCampaignList = () => useQuery({ queryKey: ["campaigns", "list"], queryFn: campaignsService.list });
