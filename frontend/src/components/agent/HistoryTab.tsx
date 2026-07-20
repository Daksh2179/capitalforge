import { useActiveAgent } from "@/hooks/useActiveAgent";
import { useOrders } from "@/hooks/useOrders";

export function HistoryTab() {
  const { activeAgent, isLoading: agentLoading } = useActiveAgent();
  const { data: orders, isLoading: ordersLoading } = useOrders(activeAgent?.id ?? null, 100);

  if (agentLoading || ordersLoading) {
    return <p className="text-muted-foreground">Loading trade history...</p>;
  }

  if (!activeAgent) {
    return (
      <p className="text-muted-foreground">
        Your agent hasn't made any trades yet — trade history will appear
        here once it's active.
      </p>
    );
  }

  const filledTrades = (orders ?? []).filter((order) => order.status === "filled");

  if (filledTrades.length === 0) {
    return <p className="text-muted-foreground">No trades executed yet.</p>;
  }

  return (
    <div className="space-y-3">
      {filledTrades.map((order) => (
        <div key={order.id} className="flex items-center justify-between rounded-lg border border-border p-4">
          <div>
            <p className="text-sm font-medium">
              {order.side === "buy" ? "Bought" : "Sold"} {order.symbol}
            </p>
            <p className="text-xs text-muted-foreground">
              {order.filled_quantity} shares at ${order.filled_avg_price?.toFixed(2) ?? "—"}
            </p>
          </div>
          <p className="text-xs text-muted-foreground">
            {order.filled_at ? new Date(order.filled_at).toLocaleString() : "—"}
          </p>
        </div>
      ))}
    </div>
  );
}