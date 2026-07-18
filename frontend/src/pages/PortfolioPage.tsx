import { usePortfolioHoldings } from "@/hooks/usePortfolio";
import { PortfolioSummary } from "@/components/portfolio/PortfolioSummary";
import { PortfolioHoldingRow } from "@/components/portfolio/PortfolioHoldingRow";

export function PortfolioPage() {
  const { data: holdings, isLoading } = usePortfolioHoldings();

  if (isLoading) {
    return <p className="text-muted-foreground">Loading your portfolio...</p>;
  }

  const sorted = [...(holdings ?? [])].sort((a, b) => a.symbol.localeCompare(b.symbol));

  return (
    <div>
      <h1 className="mb-6 text-2xl font-semibold">Portfolio</h1>
      <PortfolioSummary holdings={holdings ?? []} />
      {sorted.length > 0 && (
        <div className="space-y-3">
          {sorted.map((holding) => (
            <PortfolioHoldingRow key={holding.id} holding={holding} />
          ))}
        </div>
      )}
    </div>
  );
}