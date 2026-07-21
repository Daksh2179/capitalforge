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

/**
 * Never throws. Malformed or unexpected input (missing fields, old
 * pre-rename shapes, an unrecognized type) returns an explicit,
 * visible fallback string rather than crashing the DraftPane — this
 * keeps the UI alive while still making it obvious during development
 * that something is wrong, rather than silently hiding it.
 */
export function formatCapitalAllocation(
  allocation: CapitalAllocation | null | undefined
): string {
  if (!allocation || typeof allocation !== "object" || !("type" in allocation)) {
    if (import.meta.env.DEV) {
      console.warn("formatCapitalAllocation received malformed data:", allocation);
    }
    return "Invalid capital allocation";
  }

  switch (allocation.type) {
    case "percentage_of_portfolio":
      return typeof allocation.percentage === "number"
        ? `${allocation.percentage}% of portfolio`
        : "Invalid capital allocation";
    case "fixed_capital":
      return typeof allocation.capital_usd === "number"
        ? `$${allocation.capital_usd.toLocaleString()} allocated`
        : "Invalid capital allocation";
    case "share_count":
      return typeof allocation.shares === "number"
        ? `${allocation.shares} shares`
        : "Invalid capital allocation";
    default:
      if (import.meta.env.DEV) {
        console.warn("formatCapitalAllocation received unknown type:", allocation);
      }
      return "Unknown allocation";
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