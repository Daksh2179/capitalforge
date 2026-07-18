import { useParams } from "react-router-dom";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { useQuote } from "@/hooks/useQuote";
import { useHistory } from "@/hooks/useHistory";
import { useAddToPortfolio, usePortfolioHoldings } from "@/hooks/usePortfolio";
import { Button } from "@/components/ui/button";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL as string;

export function StockDetailPage() {
  const { symbol } = useParams<{ symbol: string }>();
  const sym = symbol ?? "";

  const { data: quote, isLoading: quoteLoading } = useQuote(sym);
  const { data: history, isLoading: historyLoading } = useHistory(sym);
  const { data: holdings } = usePortfolioHoldings();
  const addToPortfolio = useAddToPortfolio();

  const alreadyAdded = holdings?.some((h) => h.symbol === sym) ?? false;

  const chartData = (history ?? []).map((bar) => ({
    date: new Date(bar.timestamp).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
    close: bar.close,
  }));

  return (
    <div>
      <div className="mb-6 flex items-center gap-4">
        <img
          src={`${API_BASE_URL}/logos/${sym}`}
          alt={`${sym} logo`}
          width={56}
          height={56}
          className="rounded-md"
        />
        <div className="flex-1">
          <h1 className="text-2xl font-semibold">{sym}</h1>
          {quoteLoading && <p className="text-sm text-muted-foreground">Loading price...</p>}
          {quote && <p className="text-lg text-muted-foreground">${quote.price.toFixed(2)}</p>}
        </div>
        <Button
          onClick={() => addToPortfolio.mutate(sym)}
          disabled={alreadyAdded || addToPortfolio.isPending}
          variant={alreadyAdded ? "outline" : "default"}
        >
          {alreadyAdded ? "✓ In Portfolio" : "Add to Portfolio"}
        </Button>
      </div>

      <div className="h-80 rounded-lg border border-border p-4">
        {historyLoading && <p className="text-sm text-muted-foreground">Loading chart...</p>}
        {!historyLoading && chartData.length === 0 && (
          <p className="text-sm text-muted-foreground">No historical data available.</p>
        )}
        {chartData.length > 0 && (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <XAxis dataKey="date" tick={{ fontSize: 12 }} />
              <YAxis domain={["auto", "auto"]} tick={{ fontSize: 12 }} width={60} />
              <Tooltip />
              <Line type="monotone" dataKey="close" stroke="currentColor" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}