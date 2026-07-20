import { useQuery } from "@tanstack/react-query";
import { getHistory } from "@/api/market";

const SNAPSHOT_SYMBOLS = ["SPY", "QQQ", "DIA"] as const;

export interface SnapshotItem {
  symbol: string;
  price: number;
  change: number;
  changePct: number;
}

export function useMarketSnapshot() {
  return useQuery({
    queryKey: ["market", "snapshot"],
    queryFn: async (): Promise<SnapshotItem[]> => {
      const results = await Promise.all(
        SNAPSHOT_SYMBOLS.map(async (symbol) => {
          const bars = await getHistory(symbol, 5);
          if (bars.length < 2) {
            return { symbol, price: bars[0]?.close ?? 0, change: 0, changePct: 0 };
          }
          const latest = bars[bars.length - 1].close;
          const previous = bars[bars.length - 2].close;
          const change = latest - previous;
          const changePct = (change / previous) * 100;
          return { symbol, price: latest, change, changePct };
        })
      );
      return results;
    },
    staleTime: 60_000,
  });
}