import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { addHolding, listHoldings } from "@/api/portfolio";
import { useCurrentUser } from "@/lib/constants";

export function usePortfolioHoldings() {
  const { userId } = useCurrentUser();
  return useQuery({
    queryKey: ["portfolio", "holdings", userId],
    queryFn: () => listHoldings(userId),
  });
}

export function useAddToPortfolio() {
  const { userId } = useCurrentUser();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (symbol: string) => addHolding(userId, symbol),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolio", "holdings", userId] });
    },
  });
}