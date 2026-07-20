import { useMarketSnapshot } from "@/hooks/useMarketSnapshot";
import { cn } from "@/lib/utils";

export function MarketSnapshot() {
  const { data, isLoading } = useMarketSnapshot();

  if (isLoading) {
    return <p className="mb-4 text-xs text-muted-foreground">Loading market snapshot...</p>;
  }

  return (
    <div className="mb-6 flex gap-6 rounded-lg border border-border px-4 py-3">
      {data?.map((item) => {
        const isUp = item.change >= 0;
        return (
          <div key={item.symbol} className="flex items-baseline gap-2">
            <span className="text-sm font-medium">{item.symbol}</span>
            <span className="text-sm text-muted-foreground">${item.price.toFixed(2)}</span>
            <span
              className={cn(
                "text-xs font-medium",
                isUp ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"
              )}
            >
              {isUp ? "▲" : "▼"} {Math.abs(item.changePct).toFixed(2)}%
            </span>
          </div>
        );
      })}
    </div>
  );
}