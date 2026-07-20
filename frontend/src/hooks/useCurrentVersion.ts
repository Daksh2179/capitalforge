import { useQuery } from "@tanstack/react-query";
import { getCurrentVersion } from "@/api/strategies";

export function useCurrentVersion(strategyId: string | null) {
  return useQuery({
    queryKey: ["strategies", strategyId, "current-version"],
    queryFn: () => getCurrentVersion(strategyId as string),
    enabled: strategyId !== null,
  });
}