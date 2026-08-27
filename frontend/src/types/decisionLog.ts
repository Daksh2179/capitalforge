// Mirrors DecisionLogResponse

export interface DecisionLogResponse {
  id: string;
  strategy_version_id: string;
  timestamp: string;
  market_snapshot_json: Record<string, unknown>;
  rules_triggered_json: string[];
  action_taken: string;
  risk_approved: boolean;
  risk_reason: string;
  // "selected" | "deferred" | "skipped_liquidity" | "skipped_paused" |
  // null (SELLs and HOLDs never reach the planner, so this is null for
  // those -- null is not itself meaningful beyond "not a BUY-planning
  // outcome").
  plan_outcome: string | null;
  explanation_text: string | null;
  created_at: string;
}