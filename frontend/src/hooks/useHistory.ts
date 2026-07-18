import { useQuery } from "@tanstack/react-query";
import { getHistory } from "@/api/market";

export function useHistory(symbol: string) {
  return useQuery({
    queryKey: ["market", "history", symbol],
    queryFn: () => getHistory(symbol),
    staleTime: 5 * 60_000, // historical bars don't need frequent refetching
  });
}