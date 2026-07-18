import { useState } from "react";
import { SymbolSearch } from "@/components/markets/SymbolSearch";
import { StockCard } from "@/components/markets/StockCard";

export function MarketsPage() {
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>([]);

  function handleSelect(symbol: string) {
    setSelectedSymbols((prev) => (prev.includes(symbol) ? prev : [...prev, symbol]));
  }

  return (
    <div>
      <div className="mb-8 rounded-lg border border-border bg-muted/30 px-6 py-8 text-center">
        <h1 className="text-2xl font-semibold">CapitalForge</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Browse stocks, set the rules for how you want to trade them, and let
          your AI Trading Agent handle execution on your paper account.
        </p>
      </div>

      <SymbolSearch onSelect={handleSelect} />

      {selectedSymbols.length === 0 ? (
        <p className="text-muted-foreground">
          Search for a stock above, or check back soon for Featured Stocks.
        </p>
      ) : (
        <div className="space-y-3">
          {selectedSymbols.map((symbol) => (
            <StockCard key={symbol} symbol={symbol} />
          ))}
        </div>
      )}
    </div>
  );
}