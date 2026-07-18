import { useState } from "react";
import { useSearchAssets } from "@/hooks/useSearchAssets";

interface SymbolSearchProps {
  onSelect: (symbol: string) => void;
}

export function SymbolSearch({ onSelect }: SymbolSearchProps) {
  const [query, setQuery] = useState("");
  const { data: results, isFetching } = useSearchAssets(query);

  function handleSelect(symbol: string) {
    onSelect(symbol);
    setQuery("");
  }

  return (
    <div className="relative mb-6">
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search by ticker or company name (e.g. AAPL or Apple)"
        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />

      {query.trim().length > 0 && (
        <div className="absolute z-10 mt-1 w-full rounded-md border border-border bg-background shadow-md">
          {isFetching && (
            <p className="px-3 py-2 text-sm text-muted-foreground">Searching...</p>
          )}
          {!isFetching && results && results.length === 0 && (
            <p className="px-3 py-2 text-sm text-muted-foreground">No results found.</p>
          )}
          {!isFetching &&
            results?.map((entry) => (
              <button
                key={entry.symbol}
                onClick={() => handleSelect(entry.symbol)}
                className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-muted"
              >
                <span className="font-medium">{entry.symbol}</span>
                <span className="ml-2 truncate text-muted-foreground">{entry.name}</span>
              </button>
            ))}
        </div>
      )}
    </div>
  );
}