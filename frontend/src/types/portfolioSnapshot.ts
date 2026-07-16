// Mirrors PortfolioSnapshotResponse

export interface PortfolioSnapshotResponse {
  id: string;
  strategy_id: string;
  timestamp: string;
  cash_balance: number;
  positions_json: Record<string, unknown>;
  total_value: number;
}