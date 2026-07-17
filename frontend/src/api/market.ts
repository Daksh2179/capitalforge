// Typed functions for market data endpoints

import { apiRequest } from "./client";
import type { QuoteResponse } from "@/types/market";

export function getQuote(symbol: string): Promise<QuoteResponse> {
  return apiRequest<QuoteResponse>(`/market/${symbol}/quote`);
}