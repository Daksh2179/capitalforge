// Mirrors backend schemas/agent.py

import type { StrategyConfig, StrategyResponse } from "./strategy";

export type TranslationStatus =
  | "updated_draft"
  | "needs_clarification"
  | "needs_disambiguation"
  | "error";

export interface AppliedOperation {
  operation: string;
  symbol?: string | null;
  description: string;
}

export interface TranslateRequest {
  conversation_id: string;
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