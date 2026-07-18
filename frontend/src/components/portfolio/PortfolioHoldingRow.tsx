import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useQuote } from "@/hooks/useQuote";
import { useAddToPortfolio, useRemoveFromPortfolio } from "@/hooks/usePortfolio";
import { cn } from "@/lib/utils";
import type { PortfolioHoldingResponse } from "@/types/portfolio";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL as string;

interface PortfolioHoldingRowProps {
  holding: PortfolioHoldingResponse;
}

export function PortfolioHoldingRow({ holding }: PortfolioHoldingRowProps) {
  const { data: quote } = useQuote(holding.symbol);
  const removeHolding = useRemoveFromPortfolio();
  const addHolding = useAddToPortfolio();

  function handleRemove() {
    const symbol = holding.symbol;
    removeHolding.mutate(symbol, {
      onSuccess: () => {
        toast(`Removed ${symbol}`, {
          action: {
            label: "Undo",
            onClick: () => addHolding.mutate(symbol),
          },
        });
      },
    });
  }

  return (
    <div className="flex items-center gap-4 rounded-lg border border-border p-4">
      <img
        src={`${API_BASE_URL}/logos/${holding.symbol}`}
        alt={`${holding.symbol} logo`}
        width={40}
        height={40}
        className="rounded-md"
      />
      <div className="flex-1">
        <h3 className="font-medium">{holding.symbol}</h3>
        {quote && <p className="text-sm text-muted-foreground">${quote.price.toFixed(2)}</p>}
      </div>
      <span
        className={cn(
          "rounded-full px-3 py-1 text-xs font-medium",
          holding.is_ai_configured
            ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
            : "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300"
        )}
      >
        {holding.is_ai_configured ? "Agent Assigned" : "Agent Not Assigned"}
      </span>
      <Button variant="ghost" size="sm" onClick={handleRemove} disabled={removeHolding.isPending}>
        Remove
      </Button>
    </div>
  );
}