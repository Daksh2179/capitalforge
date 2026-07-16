// Mirrors OrderResponse

export interface OrderResponse {
  id: string;
  strategy_version_id: string;
  alpaca_order_id: string;
  symbol: string;
  side: string;
  order_type: string;
  quantity: number;
  status: string;
  limit_price: number | null;
  stop_price: number | null;
  filled_quantity: number;
  filled_avg_price: number | null;
  submitted_at: string;
  filled_at: string | null;
}