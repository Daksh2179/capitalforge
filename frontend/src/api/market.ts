// Typed functions for market data endpoints

import { apiRequest } from "./client";
import type { QuoteResponse, AssetEntry } from "@/types/market";

export function getQuote(symbol: string): Promise<QuoteResponse> {
  return apiRequest<QuoteResponse>(`/market/${symbol}/quote`);
}

export function searchAssets(query: string): Promise<AssetEntry[]> {
  return apiRequest<AssetEntry[]>("/market/search", {
    searchParams: { q: query },
  });
}