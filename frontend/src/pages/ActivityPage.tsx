import { useActiveAgent } from "@/hooks/useActiveAgent";
import { usePortfolioSnapshots } from "@/hooks/usePortfolioSnapshots";
import { useOrders } from "@/hooks/useOrders";
import { parsePositions } from "@/lib/parsePortfolioSnapshot";

export function ActivityPage() {
  const { activeAgent, isLoading: agentLoading } = useActiveAgent();
  const { data: snapshots, isLoading: snapshotsLoading } = usePortfolioSnapshots(activeAgent?.id ?? null, 1);
  const { data: orders, isLoading: ordersLoading } = useOrders(activeAgent?.id ?? null, 50);

  if (agentLoading) {
    return <p className="text-muted-foreground">Loading your account...</p>;
  }

  if (!activeAgent) {
    return (
      <div className="rounded-lg border border-border p-6 text-center">
        <p className="text-muted-foreground">
          There's no confirmed agent yet, so there's no real account activity to
          show. Head to the AI Agent tab to build and confirm a strategy first.
        </p>
      </div>
    );
  }

  // list_portfolio_snapshots orders by timestamp desc, so [0] is the latest.
  const latestSnapshot = snapshots?.[0];
  const positions = latestSnapshot ? parsePositions(latestSnapshot.positions_json) : [];
  const positionsValue = latestSnapshot ? latestSnapshot.total_value - latestSnapshot.cash_balance : null;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Activity</h1>

      <div className="rounded-lg border border-border p-6">
        <h3 className="mb-3 text-sm font-medium text-muted-foreground">Account Value</h3>
        {snapshotsLoading && <p className="text-sm text-muted-foreground">Loading...</p>}
        {!snapshotsLoading && !latestSnapshot && (
          <p className="text-sm text-muted-foreground">
            No snapshot recorded yet -- this fills in after the strategy's first
            evaluation cycle runs.
          </p>
        )}
        {latestSnapshot && (
          <div className="grid grid-cols-3 gap-4">
            <div>
              <p className="text-xs text-muted-foreground">Total Value</p>
              <p className="text-lg font-semibold">${latestSnapshot.total_value.toLocaleString()}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Cash</p>
              <p className="text-lg font-semibold">${latestSnapshot.cash_balance.toLocaleString()}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">In Positions</p>
              <p className="text-lg font-semibold">
                {positionsValue !== null ? `$${positionsValue.toLocaleString()}` : "--"}
              </p>
            </div>
          </div>
        )}
      </div>

      <div className="rounded-lg border border-border p-6">
        <h3 className="mb-3 text-sm font-medium text-muted-foreground">Holdings</h3>
        {snapshotsLoading && <p className="text-sm text-muted-foreground">Loading...</p>}
        {!snapshotsLoading && latestSnapshot && positions.length === 0 && (
          <p className="text-sm text-muted-foreground">No open positions right now.</p>
        )}
        {positions.length > 0 && (
          <div className="space-y-2">
            {positions.map((position) => (
              <div
                key={position.symbol}
                className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm"
              >
                <span className="font-medium">{position.symbol}</span>
                <span className="text-muted-foreground">
                  {position.quantity} shares @ ${position.averageEntryPrice.toFixed(2)} avg
                </span>
                <span className="font-medium">
                  {position.marketValue !== null ? `$${position.marketValue.toFixed(2)}` : "--"}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-lg border border-border p-6">
        <h3 className="mb-3 text-sm font-medium text-muted-foreground">Recent Orders</h3>
        {ordersLoading && <p className="text-sm text-muted-foreground">Loading...</p>}
        {!ordersLoading && (!orders || orders.length === 0) && (
          <p className="text-sm text-muted-foreground">No orders placed yet.</p>
        )}
        {orders && orders.length > 0 && (
          <div className="space-y-2">
            {orders.map((order) => (
              <div
                key={order.id}
                className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm"
              >
                <span>
                  <span className="font-medium">{order.side === "buy" ? "Bought" : "Sold"}</span>{" "}
                  {order.symbol}
                </span>
                <span className="text-muted-foreground">
                  {order.filled_quantity > 0
                    ? `${order.filled_quantity} @ $${order.filled_avg_price?.toFixed(2) ?? "--"}`
                    : `${order.quantity} requested`}
                </span>
                <span className="text-xs uppercase text-muted-foreground">{order.status}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}