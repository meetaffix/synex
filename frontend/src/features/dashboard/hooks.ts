import { useQuery } from "@tanstack/react-query";
import { dashboardService, type DashboardFilters, type Granularity } from "./service";

export const useSummary = (filters: DashboardFilters) =>
  useQuery({ queryKey: ["dashboard", "summary", filters], queryFn: () => dashboardService.summary(filters), retry: false });

export const useTimeseries = (filters: DashboardFilters, granularity: Granularity) =>
  useQuery({ queryKey: ["dashboard", "series", filters, granularity], queryFn: () => dashboardService.timeseries(filters, granularity), retry: false });

export const useAccountStats = (filters: DashboardFilters) =>
  useQuery({ queryKey: ["dashboard", "accounts", filters], queryFn: () => dashboardService.accounts(filters), retry: false });
