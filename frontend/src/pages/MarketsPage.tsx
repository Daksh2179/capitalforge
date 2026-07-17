import { useState } from "react";
import { SymbolSearch } from "@/components/markets/SymbolSearch";
import { StockCard } from "@/components/markets/StockCard";

export function MarketsPage() {
  const [symbols, setSymbols] = useState<string[]>([]);

  function handleSearch(symbol: string) {
    setSymbols((prev) => (prev.includes(symbol) ? prev : [...prev, symbol]));
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

      <SymbolSearch onSearch={handleSearch} />

      {symbols.length === 0 ? (
        <p className="text-muted-foreground">
          Search for a stock symbol to see its price and set up trading rules.
        </p>
      ) : (
        <div className="space-y-3">
          {symbols.map((symbol) => (
            <StockCard key={symbol} symbol={symbol} />
          ))}
        </div>
      )}
    </div>
  );
}