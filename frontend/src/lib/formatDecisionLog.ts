// Plain-English labels/colors for a DecisionLogResponse row. Never
// throws on an unrecognized value -- falls back to showing the raw
// string rather than hiding it, since an unrecognized value is more
// useful visible than swallowed.

import type { DecisionLogResponse } from "@/types/decisionLog";

export function getLogSymbol(log: DecisionLogResponse): string {
  const symbol = log.market_snapshot_json.symbol;
  return typeof symbol === "string" ? symbol : "Unknown";
}

export function formatActionTaken(actionTaken: string): string {
  switch (actionTaken) {
    case "buy":
      return "Buy triggered";
    case "sell":
      return "Sell triggered";
    case "hold":
      return "Held";
    default:
      return actionTaken;
  }
}

/**
 * plan_outcome is only ever set for a BUY signal that reached (or was
 * deliberately kept from reaching) the Opportunity Engine -- null for
 * every SELL and every HOLD, which is itself meaningful ("this row
 * isn't about buy-planning"), not an error state.
 */
export function formatPlanOutcome(planOutcome: string | null): string | null {
  if (planOutcome === null) return null;
  switch (planOutcome) {
    case "selected":
      return "Selected for execution";
    case "deferred":
      return "Deferred (lost capital competition)";
    case "skipped_liquidity":
      return "Skipped (insufficient liquidity)";
    case "skipped_paused":
      return "Skipped (strategy paused)";
    default:
      return planOutcome;
  }
}

export function getOutcomeColor(log: DecisionLogResponse): string {
  if (log.action_taken !== "hold" && log.risk_approved) {
    return "text-emerald-600 dark:text-emerald-400";
  }
  if (log.plan_outcome === "skipped_paused" || log.plan_outcome === "skipped_liquidity" || log.plan_outcome === "deferred") {
    return "text-amber-600 dark:text-amber-400";
  }
  if (log.action_taken === "hold") {
    return "text-muted-foreground";
  }
  return "text-destructive";
}