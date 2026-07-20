// Plain-English rendering of StrategyConfig pieces. Shared by the
// Chat draft pane and (later) the Agent Rules tab — same underlying
// data, same translation into human-readable text.

import type {
  AssetRule,
  CapitalAllocation,
  ConditionGroup,
  RuleCondition,
} from "@/types/strategy";

function formatCondition(rule: RuleCondition): string {
  const indicator =
    rule.indicator === "PRICE" ? "price" : `${rule.indicator}(${rule.period})`;

  switch (rule.operator) {
    case "less_than":
      return `${indicator} < ${rule.value}`;
    case "greater_than":
      return `${indicator} > ${rule.value}`;
    case "price_above":
      return `price above ${indicator}`;
    case "price_below":
      return `price below ${indicator}`;
    case "crosses_above":
      return rule.compare_indicator
        ? `${indicator} crosses above ${rule.compare_indicator}(${rule.compare_period})`
        : `${indicator} crosses above ${rule.value}`;
    case "crosses_below":
      return rule.compare_indicator
        ? `${indicator} crosses below ${rule.compare_indicator}(${rule.compare_period})`
        : `${indicator} crosses below ${rule.value}`;
    case "pct_below":
      return `price ${rule.value}% below ${indicator}`;
    case "pct_above":
      return `price ${rule.value}% above ${indicator}`;
    default:
      return indicator;
  }
}

export function formatCapitalAllocation(allocation: CapitalAllocation): string {
  switch (allocation.type) {
    case "percentage_of_portfolio":
      return `${allocation.percentage}% of portfolio`;
    case "fixed_capital":
      return `$${allocation.capital_usd?.toLocaleString()} allocated`;
    case "share_count":
      return `${allocation.shares} shares`;
    default:
      return "";
  }
}

export function formatConditionGroup(group: ConditionGroup): string {
  if (group.rules.length === 0) {
    return "(no conditions set)";
  }
  const joiner = group.operator === "AND" ? " and " : " or ";
  return group.rules.map(formatCondition).join(joiner);
}

export function formatAssetRule(rule: AssetRule): {
  symbol: string;
  buy: string;
  sell: string;
  sizing: string;
  exit: string | null;
} {
  const exitParts: string[] = [];
  if (rule.exit.stop_loss_pct != null) {
    exitParts.push(`stop-loss at ${rule.exit.stop_loss_pct}%`);
  }
  if (rule.exit.take_profit_pct != null) {
    exitParts.push(`take-profit at ${rule.exit.take_profit_pct}%`);
  }

  return {
    symbol: rule.symbol,
    buy: formatConditionGroup(rule.buy_conditions),
    sell: formatConditionGroup(rule.sell_conditions),
    sizing: formatCapitalAllocation(rule.capital_allocation),
    exit: exitParts.length > 0 ? exitParts.join(", ") : null,
  };
}