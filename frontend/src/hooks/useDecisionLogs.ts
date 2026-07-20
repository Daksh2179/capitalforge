import { useQuery } from "@tanstack/react-query";
import { getDecisionLogs } from "@/api/strategies";

export function useDecisionLogs(strategyId: string | null, limit: number = 50) {
  return useQuery({
    queryKey: ["strategies", strategyId, "decision-logs", limit],
    queryFn: () => getDecisionLogs(strategyId as string, limit),
    enabled: strategyId !== null,
    refetchInterval: 30_000, // matches the polling cadence discussed for activity-style data
  });
}