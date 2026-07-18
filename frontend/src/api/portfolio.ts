import { apiRequest } from "./client";
import type { PortfolioHoldingResponse } from "@/types/portfolio";

export function addHolding(userId: string, symbol: string): Promise<PortfolioHoldingResponse> {
  return apiRequest<PortfolioHoldingResponse>("/portfolio/holdings", {
    method: "POST",
    body: { user_id: userId, symbol },
  });
}

export function listHoldings(userId: string): Promise<PortfolioHoldingResponse[]> {
  return apiRequest<PortfolioHoldingResponse[]>("/portfolio/holdings", {
    searchParams: { user_id: userId },
  });
}

export function removeHolding(userId: string, symbol: string): Promise<void> {
  return apiRequest<void>(`/portfolio/holdings/${symbol}`, {
    method: "DELETE",
    searchParams: { user_id: userId },
  });
}