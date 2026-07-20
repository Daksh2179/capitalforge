import { useQuery } from "@tanstack/react-query";
import { listStrategies } from "@/api/strategies";
import { useCurrentUser } from "@/lib/constants";
import type { StrategyResponse } from "@/types/strategy";

/**
 * Finds the user's one active/confirmed Agent (a Strategy in any
 * non-draft state). V1 assumes at most one — matches the single-agent
 * constraint used throughout the rest of the app. Returns null if the
 * user has never confirmed anything yet, distinct from "loading."
 */
export function useActiveAgent() {
  const { userId } = useCurrentUser();

  const query = useQuery({
    queryKey: ["strategies", "list", userId],
    queryFn: () => listStrategies(userId),
  });

  const activeAgent: StrategyResponse | null =
    query.data?.find((s) => s.state !== "draft") ?? null;

  return { activeAgent, isLoading: query.isLoading };
}