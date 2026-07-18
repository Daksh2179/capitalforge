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