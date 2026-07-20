// Mirrors backend schemas/strategy.py

export type Indicator = "PRICE" | "RSI" | "SMA" | "EMA" | "ROLLING_HIGH";

export type ConditionOperator =
  | "less_than"
  | "greater_than"
  | "price_above"
  | "price_below"
  | "crosses_above"
  | "crosses_below"
  | "pct_below"
  | "pct_above";

export interface RuleCondition {
  indicator: Indicator;
  period: number;
  operator: ConditionOperator;
  value?: number | null;
  compare_indicator?: Indicator | null;
  compare_period?: number | null;
}

export interface ConditionGroup {
  operator: "AND" | "OR";
  rules: RuleCondition[];
}

export type AllocationType =
  | "percentage_of_portfolio"
  | "fixed_capital"
  | "share_count";

export interface CapitalAllocation {
  type: AllocationType;
  percentage?: number | null;
  capital_usd?: number | null;
  shares?: number | null;
}

export interface ExitRules {
  stop_loss_pct?: number | null;
  take_profit_pct?: number | null;
}

export interface AssetRule {
  symbol: string;
  buy_conditions: ConditionGroup;
  sell_conditions: ConditionGroup;
  capital_allocation: CapitalAllocation;
  exit: ExitRules;
}

export interface PortfolioRules {
  cash_reserve_pct?: number | null;
  max_allocation_pct?: number | null;
  max_open_positions?: number | null;
  total_capital_usd?: number | null;
}

export interface StrategyConfig {
  schema_version: 2;
  portfolio_rules: PortfolioRules;
  asset_rules: AssetRule[];
}

export type StrategyVersionSource = "manual" | "chat";

export type StrategyState =
  | "draft"
  | "validated"
  | "backtested"
  | "confirmed"
  | "active"
  | "paused"
  | "closed";

export interface StrategyResponse {
  id: string;
  user_id: string;
  state: StrategyState;
  current_version_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface StrategyVersionResponse {
  id: string;
  strategy_id: string;
  version_number: number;
  config_json: StrategyConfig;
  source: StrategyVersionSource;
  confirmed_at: string | null;
  created_at: string;
}

export interface StrategyCreateRequest {
  user_id: string;
  config: StrategyConfig;
  source: StrategyVersionSource;
}

export interface StrategyVersionCreateRequest {
  config: StrategyConfig;
  source: StrategyVersionSource;
}