// Typed functions for strategy endpoints

import { apiRequest } from "./client";
import type {
  StrategyCreateRequest,
  StrategyResponse,
  StrategyVersionCreateRequest,
  StrategyVersionResponse,
} from "@/types/strategy";
import type { DecisionLogResponse } from "@/types/decisionLog";
import type { OrderResponse } from "@/types/order";
import type { PortfolioSnapshotResponse } from "@/types/portfolioSnapshot";
import type { BacktestStructuredResult } from "@/types/backtest";

export function listStrategies(userId: string): Promise<StrategyResponse[]> {
  return apiRequest<StrategyResponse[]>("/strategies", {
    searchParams: { user_id: userId },
  });
}

export function getStrategy(strategyId: string): Promise<StrategyResponse> {
  return apiRequest<StrategyResponse>(`/strategies/${strategyId}`);
}

export function createStrategy(
  payload: StrategyCreateRequest
): Promise<StrategyResponse> {
  return apiRequest<StrategyResponse>("/strategies", {
    method: "POST",
    body: payload,
  });
}

export function createStrategyVersion(
  strategyId: string,
  payload: StrategyVersionCreateRequest
): Promise<StrategyVersionResponse> {
  return apiRequest<StrategyVersionResponse>(
    `/strategies/${strategyId}/versions`,
    { method: "POST", body: payload }
  );
}

export function getDecisionLogs(
  strategyId: string,
  limit?: number
): Promise<DecisionLogResponse[]> {
  return apiRequest<DecisionLogResponse[]>(
    `/strategies/${strategyId}/decision-logs`,
    { searchParams: { limit } }
  );
}

export function getOrders(
  strategyId: string,
  limit?: number
): Promise<OrderResponse[]> {
  return apiRequest<OrderResponse[]>(`/strategies/${strategyId}/orders`, {
    searchParams: { limit },
  });
}

export function getPortfolioSnapshots(
  strategyId: string,
  limit?: number
): Promise<PortfolioSnapshotResponse[]> {
  return apiRequest<PortfolioSnapshotResponse[]>(
    `/strategies/${strategyId}/portfolio-snapshots`,
    { searchParams: { limit } }
  );
}

export function getCurrentVersion(strategyId: string): Promise<StrategyVersionResponse> {
  return apiRequest<StrategyVersionResponse>(`/strategies/${strategyId}/current-version`);
}

// Add near the other functions, using the same apiRequest pattern
export function pauseStrategy(strategyId: string): Promise<StrategyResponse> {
  return apiRequest<StrategyResponse>(`/strategies/${strategyId}/pause`, {
    method: "POST",
  });
}

export function resumeStrategy(strategyId: string): Promise<StrategyResponse> {
  return apiRequest<StrategyResponse>(`/strategies/${strategyId}/resume`, {
    method: "POST",
  });
}

export function getBacktest(
  strategyId: string,
  days?: number
): Promise<BacktestStructuredResult> {
  return apiRequest<BacktestStructuredResult>(`/strategies/${strategyId}/backtest`, {
    searchParams: { days },
  });
}