// Safe parsing for PortfolioSnapshotResponse.positions_json, whose
// real shape (from trading_cycle_service.record_portfolio_snapshot)
// is Record<symbol, { quantity, average_entry_price, current_price }>
// -- but the API types it as Record<string, unknown> since JSONB has
// no schema at the type level. Never throws: a malformed entry is
// dropped with a dev-only warning, same convention as
// formatCapitalAllocation, so one bad row can't blank the whole page.

export interface ParsedPosition {
  symbol: string;
  quantity: number;
  averageEntryPrice: number;
  currentPrice: number | null;
  marketValue: number | null;
}

export function parsePositions(positionsJson: Record<string, unknown>): ParsedPosition[] {
  const positions: ParsedPosition[] = [];

  for (const [symbol, raw] of Object.entries(positionsJson)) {
    if (typeof raw !== "object" || raw === null) {
      if (import.meta.env.DEV) {
        console.warn(`parsePositions: skipping malformed entry for ${symbol}`, raw);
      }
      continue;
    }

    const entry = raw as Record<string, unknown>;
    const quantity = entry.quantity;
    const averageEntryPrice = entry.average_entry_price;
    const currentPrice = entry.current_price;

    if (typeof quantity !== "number" || typeof averageEntryPrice !== "number") {
      if (import.meta.env.DEV) {
        console.warn(`parsePositions: skipping entry with missing required fields for ${symbol}`, raw);
      }
      continue;
    }

    const parsedCurrentPrice = typeof currentPrice === "number" ? currentPrice : null;

    positions.push({
      symbol,
      quantity,
      averageEntryPrice,
      currentPrice: parsedCurrentPrice,
      marketValue: parsedCurrentPrice !== null ? quantity * parsedCurrentPrice : null,
    });
  }

  return positions.sort((a, b) => a.symbol.localeCompare(b.symbol));
}