import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useQuote } from "@/hooks/useQuote";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL as string;

interface StockCardProps {
  symbol: string;
}

export function StockCard({ symbol }: StockCardProps) {
  const navigate = useNavigate();
  const { data: quote, isLoading, isError } = useQuote(symbol);

  function handleSetupRules() {
    navigate("/agent", { state: { prefillSymbol: symbol } });
  }

  return (
    <div className="flex items-center gap-4 rounded-lg border border-border p-4">
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
      <Button onClick={handleSetupRules} disabled={isLoading || isError}>
        Set up trading rules
      </Button>
    </div>
  );
}