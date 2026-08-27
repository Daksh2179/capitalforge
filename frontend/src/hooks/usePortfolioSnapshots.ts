import { useQuery } from "@tanstack/react-query";
import { getPortfolioSnapshots } from "@/api/strategies";

export function usePortfolioSnapshots(strategyId: string | null, limit: number = 100) {
  return useQuery({
    queryKey: ["strategies", strategyId, "portfolio-snapshots", limit],
    queryFn: () => getPortfolioSnapshots(strategyId as string, limit),
    enabled: strategyId !== null,
    refetchInterval: 30_000, // matches useDecisionLogs/useOrders' polling cadence
  });
}