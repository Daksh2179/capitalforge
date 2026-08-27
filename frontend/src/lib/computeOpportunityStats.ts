// Tallies real, persisted DecisionLog rows -- no computation the
// backend hasn't already done. Only BUY-side rows ever carry a
// plan_outcome (SELLs and HOLDs never reach the Opportunity Engine),
// so this is scoped to action_taken === "buy" rows specifically.

import type { DecisionLogResponse } from "@/types/decisionLog";

export interface OpportunityStats {
  totalEvaluated: number;
  executed: number;
  rejectedByRisk: number;
  deferred: number;
  skippedLiquidity: number;
  skippedPaused: number;
}

export function computeOpportunityStats(logs: DecisionLogResponse[]): OpportunityStats {
  const buyRows = logs.filter((log) => log.action_taken === "buy");

  let executed = 0;
  let rejectedByRisk = 0;
  let deferred = 0;
  let skippedLiquidity = 0;
  let skippedPaused = 0;

  for (const log of buyRows) {
    // "selected" means the planner chose it -- risk_approved then
    // distinguishes "actually executed" from "the real-time Risk
    // Manager rejected it at the final gate," which is a genuinely
    // different outcome from a planner-level deferral/skip.
    if (log.plan_outcome === "selected") {
      if (log.risk_approved) executed++;
      else rejectedByRisk++;
    } else if (log.plan_outcome === "deferred") {
      deferred++;
    } else if (log.plan_outcome === "skipped_liquidity") {
      skippedLiquidity++;
    } else if (log.plan_outcome === "skipped_paused") {
      skippedPaused++;
    }
  }

  return { totalEvaluated: buyRows.length, executed, rejectedByRisk, deferred, skippedLiquidity, skippedPaused };
}