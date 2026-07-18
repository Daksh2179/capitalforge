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