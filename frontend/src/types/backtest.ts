// Mirrors app/schemas/backtest.py exactly -- no calculation happens
// here, only typed shape around numbers the backend already computed.

export interface BacktestMetrics {
  symbol: string;
  period_start: string | null;
  period_end: string | null;
  starting_capital: number;
  ending_capital: number | null;
  total_return_pct: number | null;
  max_drawdown_pct: number | null;
  sharpe_ratio: number | null;
  trade_count: number;
  win_rate_pct: number | null;
}

export interface BacktestComparison {
  symbol: string;
  total_return_pct: number | null;
  max_drawdown_pct: number | null;
}

export interface BacktestStructuredResult {
  capital_label: string;
  rules: BacktestMetrics[];
  benchmarks: BacktestComparison[];
  limitations: string[];
}