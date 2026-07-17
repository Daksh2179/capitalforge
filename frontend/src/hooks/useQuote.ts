import { useQuery } from "@tanstack/react-query";
import { getQuote } from "@/api/market";

export function useQuote(symbol: string | null) {
  return useQuery({
    queryKey: ["market", "quote", symbol],
    queryFn: () => getQuote(symbol as string),
    enabled: symbol !== null && symbol.length > 0,
    retry: false, // a typo'd/invalid symbol should fail fast, not retry 3x
  });
}