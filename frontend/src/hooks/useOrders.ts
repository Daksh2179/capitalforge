import { useQuery } from "@tanstack/react-query";
import { getOrders } from "@/api/strategies";

export function useOrders(strategyId: string | null, limit: number = 100) {
  return useQuery({
    queryKey: ["strategies", strategyId, "orders", limit],
    queryFn: () => getOrders(strategyId as string, limit),
    enabled: strategyId !== null,
    refetchInterval: 30_000,
  });
}