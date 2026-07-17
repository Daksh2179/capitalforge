import { useState } from "react";
import { Button } from "@/components/ui/button";

interface SymbolSearchProps {
  onSearch: (symbol: string) => void;
}

export function SymbolSearch({ onSearch }: SymbolSearchProps) {
  const [value, setValue] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = value.trim().toUpperCase();
    if (!trimmed) return;
    onSearch(trimmed);
  }

  return (
    <form onSubmit={handleSubmit} className="mb-6 flex gap-2">
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Enter a ticker symbol (e.g. AAPL)"
        className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />
      <Button type="submit">Search</Button>
    </form>
  );
}