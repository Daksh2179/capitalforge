import { useMutation, useQueryClient } from "@tanstack/react-query";
import { pauseStrategy, resumeStrategy } from "@/api/strategies";
import { useCurrentUser } from "@/lib/constants";

/**
 * Wraps the two working REST endpoints directly -- deliberately NOT
 * routed through chat. Chat-based "pause my strategy" only produces an
 * acknowledgment message today; it never calls strategy_service or
 * changes Strategy.state (see docs/decisions.md's backend-inconsistency
 * notes). These mutations are the only real way to pause/resume.
 */
export function usePauseStrategy() {
  const { userId } = useCurrentUser();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (strategyId: string) => pauseStrategy(strategyId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["strategies", "list", userId] });
    },
  });
}

export function useResumeStrategy() {
  const { userId } = useCurrentUser();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (strategyId: string) => resumeStrategy(strategyId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["strategies", "list", userId] });
    },
  });
}