// Mirrors backend schemas/agent.py

import type { StrategyConfig, StrategyResponse } from "./strategy";

export type TranslationStatus =
  | "updated_draft"
  | "needs_clarification"
  | "needs_disambiguation"
  | "information"
  | "error";

export interface AppliedOperation {
  operation: string;
  symbol?: string | null;
  description: string;
  // None whenever the user supplied the value directly -- currently
  // only populated for a brand-new rule's capital_allocation
  // defaulting to 5%. See draft_updater.py.
  reasoning?: string | null;
  // Which PortfolioRules field this operation touched, only set for
  // set_portfolio_rule operations (e.g. "total_capital_usd").
  field?: string | null;
}

export interface TranslateRequest {
  conversation_id: string;
  user_id: string;
  message: string;
}

export interface TranslateResponse {
  status: TranslationStatus;
  draft?: StrategyConfig | null;
  applied_operations: AppliedOperation[];
  clarification_message?: string | null;
  disambiguation_message?: string | null;
  disambiguation_candidates: string[];
  error_message?: string | null;
  information_message?: string | null;
  // Always populated regardless of status -- the full composed,
  // multi-Agent narrative for this turn (includes any "Assumptions:
  // ..." disclosures folded in by the backend's ResponseComposer).
  // The forward-looking field; information_message/applied_operations
  // remain the legacy, narrower view of the same turn.
  agent_response: string;
}

export interface ConversationSessionResponse {
  messages: Record<string, unknown>[];
  draft?: StrategyConfig | null;
}

export type ValidationSeverity = "error" | "warning";

export interface ValidationIssue {
  severity: ValidationSeverity;
  symbol?: string | null;
  message: string;
}

export interface ConfirmRequest {
  user_id: string;
  conversation_id: string;
  strategy_id?: string | null;
}

export interface ConfirmRejectedResponse {
  confirmed: false;
  issues: ValidationIssue[];
}

export interface ConfirmAcceptedResponse {
  confirmed: true;
  strategy: StrategyResponse;
  warnings: ValidationIssue[];
}

export type ConfirmResponse = ConfirmAcceptedResponse | ConfirmRejectedResponse;