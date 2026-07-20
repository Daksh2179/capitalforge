import { useState } from "react";
import { SymbolSearch } from "@/components/markets/SymbolSearch";
import { FeaturedStocks } from "@/components/markets/FeaturedStocks";
import { FeaturedETFs } from "@/components/markets/FeaturedETFs";
import { StockCard } from "@/components/markets/StockCard";
import type { AssetEntry } from "@/types/market";
import { MarketSnapshot } from "@/components/markets/MarketSnapshot";

export function MarketsPage() {
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>([]);
  const [searchState, setSearchState] = useState<{
    query: string;
    results: AssetEntry[] | undefined;
    isFetching: boolean;
  }>({ query: "", results: undefined, isFetching: false });

  function handleSelect(symbol: string) {
    setSelectedSymbols((prev) => (prev.includes(symbol) ? prev : [...prev, symbol]));
  }

  const hasActiveQuery = searchState.query.trim().length > 0;
  const hasResults = searchState.results && searchState.results.length > 0;

  return (
    <div>
      <MarketSnapshot />
      <div className="mb-8 rounded-lg border border-border bg-muted/30 px-6 py-8 text-center">
        <h1 className="text-2xl font-semibold">CapitalForge</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Browse stocks, set the rules for how you want to trade them, and let
          your AI Trading Agent handle execution on your paper account.
        </p>
      </div>

      <SymbolSearch onSelect={handleSelect} onStateChange={setSearchState} />

      {selectedSymbols.length > 0 && (
        <div className="mb-8 space-y-3">
          {selectedSymbols.map((symbol) => (
            <StockCard key={symbol} symbol={symbol} />
          ))}
        </div>
      )}

      {!hasActiveQuery && (
        <div className="space-y-8">
          <FeaturedStocks />
          <FeaturedETFs />
        </div>
      )}

      {hasActiveQuery && !searchState.isFetching && !hasResults && (
        <div className="space-y-8">
          <p className="text-muted-foreground">No results found for "{searchState.query}".</p>
          <FeaturedStocks />
          <FeaturedETFs />
        </div>
      )}
    </div>
  );
}