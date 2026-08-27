import { useMutation } from "@tanstack/react-query";
import { getBacktest } from "@/api/strategies";

// A mutation, not a query -- this is explicitly user-triggered by a
// "Run Backtest" click, not something to auto-fetch or poll, matching
// the same pattern as usePauseStrategy/useResumeStrategy.
export function useRunBacktest() {
  return useMutation({
    mutationFn: ({ strategyId, days }: { strategyId: string; days?: number }) =>
      getBacktest(strategyId, days),
  });
}