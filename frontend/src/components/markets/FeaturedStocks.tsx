import { StockCard } from "./StockCard";
import { FEATURED_SYMBOLS } from "@/lib/featuredStocks";

export function FeaturedStocks() {
  return (
    <div>
      <h2 className="mb-3 text-sm font-medium text-muted-foreground">
        Featured Stocks
      </h2>
      <div className="space-y-3">
        {FEATURED_SYMBOLS.map((symbol) => (
          <StockCard key={symbol} symbol={symbol} />
        ))}
      </div>
    </div>
  );
}