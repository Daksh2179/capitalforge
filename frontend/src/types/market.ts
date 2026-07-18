// Mirrors backend schemas/market.py

export interface QuoteResponse {
  symbol: string;
  price: number;
  timestamp: string;
}

export interface AssetEntry {
  symbol: string;
  name: string;
}

export interface HistoricalBarResponse {
  timestamp: string;
  close: number;
}