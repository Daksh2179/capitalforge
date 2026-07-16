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
  explanation_text: string | null;
  created_at: string;
}