import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useQuote } from "@/hooks/useQuote";
import { useAddToPortfolio, usePortfolioHoldings } from "@/hooks/usePortfolio";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL as string;

interface StockCardProps {
  symbol: string;
}

export function StockCard({ symbol }: StockCardProps) {
  const navigate = useNavigate();
  const { data: quote, isLoading, isError } = useQuote(symbol);
  const { data: holdings } = usePortfolioHoldings();
  const addToPortfolio = useAddToPortfolio();

  const alreadyAdded = holdings?.some((h) => h.symbol === symbol) ?? false;

  function handleCardClick() {
    navigate(`/markets/${symbol}`);
  }

  function handleAddClick(e: React.MouseEvent) {
    e.stopPropagation();
    if (alreadyAdded) return;
    addToPortfolio.mutate(symbol);
  }

  const buttonLabel = addToPortfolio.isPending
    ? "Adding..."
    : alreadyAdded
      ? "✓ In Portfolio"
      : "Add to Portfolio";

  return (
    <div
      onClick={handleCardClick}
      className="flex cursor-pointer items-center gap-4 rounded-lg border border-border p-4 transition-colors hover:bg-muted/50"
    >
      <img
        src={`${API_BASE_URL}/logos/${symbol}`}
        alt={`${symbol} logo`}
        width={48}
        height={48}
        className="rounded-md"
      />
      <div className="flex-1">
        <h3 className="font-medium">{symbol}</h3>
        {isLoading && <p className="text-sm text-muted-foreground">Loading price...</p>}
        {isError && <p className="text-sm text-destructive">Couldn't load price</p>}
        {quote && <p className="text-sm text-muted-foreground">${quote.price.toFixed(2)}</p>}
      </div>
      <Button
        onClick={handleAddClick}
        disabled={isLoading || isError || alreadyAdded || addToPortfolio.isPending}
        variant={alreadyAdded ? "outline" : "default"}
      >
        {buttonLabel}
      </Button>
    </div>
  );
}