import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { searchAssets } from "@/api/market";

/**
 * Debounces the query before it ever reaches TanStack Query/the API —
 * avoids firing a request on every keystroke while the user is still
 * typing.
 */
export function useSearchAssets(query: string, debounceMs: number = 300) {
  const [debouncedQuery, setDebouncedQuery] = useState(query);

  useEffect(() => {
    const timeout = setTimeout(() => setDebouncedQuery(query), debounceMs);
    return () => clearTimeout(timeout);
  }, [query, debounceMs]);

  return useQuery({
    queryKey: ["market", "search", debouncedQuery],
    queryFn: () => searchAssets(debouncedQuery),
    enabled: debouncedQuery.trim().length > 0,
    staleTime: 60_000, // repeated identical searches within a minute don't re-fetch
  });
}