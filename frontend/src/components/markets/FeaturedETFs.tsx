import { StockCard } from "./StockCard";
import { FEATURED_ETF_SYMBOLS } from "@/lib/featuredETFs";

export function FeaturedETFs() {
  return (
    <div>
      <h2 className="mb-3 text-sm font-medium text-muted-foreground">Featured ETFs</h2>
      <div className="space-y-3">
        {FEATURED_ETF_SYMBOLS.map((symbol) => (
          <StockCard key={symbol} symbol={symbol} />
        ))}
      </div>
    </div>
  );
}