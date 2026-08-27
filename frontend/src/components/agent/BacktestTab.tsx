import { useState } from "react";
import { useActiveAgent } from "@/hooks/useActiveAgent";
import { useRunBacktest } from "@/hooks/useBacktest";
import { Button } from "@/components/ui/button";
import type { BacktestMetrics, BacktestComparison } from "@/types/backtest";

function formatPct(value: number | null): string {
  return value !== null ? `${value >= 0 ? "+" : ""}${value.toFixed(2)}%` : "--";
}

function formatMoney(value: number | null): string {
  return value !== null ? `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}` : "--";
}

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleDateString() : "--";
}

function RuleMetricsCard({ metrics }: { metrics: BacktestMetrics }) {
  const returnColor =
    metrics.total_return_pct !== null && metrics.total_return_pct >= 0
      ? "text-emerald-600 dark:text-emerald-400"
      : "text-destructive";

  return (
    <div className="rounded-lg border border-border p-4">
      <h4 className="mb-3 font-medium">{metrics.symbol}</h4>
      <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <div>
          <p className="text-xs text-muted-foreground">Period</p>
          <p>
            {formatDate(metrics.period_start)} - {formatDate(metrics.period_end)}
          </p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Starting / Ending</p>
          <p>
            {formatMoney(metrics.starting_capital)} &rarr; {formatMoney(metrics.ending_capital)}
          </p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Return</p>
          <p className={returnColor}>{formatPct(metrics.total_return_pct)}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Max Drawdown</p>
          <p>{formatPct(metrics.max_drawdown_pct)}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Sharpe Ratio</p>
          <p>{metrics.sharpe_ratio !== null ? metrics.sharpe_ratio.toFixed(2) : "--"}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Trades</p>
          <p>{metrics.trade_count}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Win Rate</p>
          <p>{metrics.win_rate_pct !== null ? `${metrics.win_rate_pct.toFixed(0)}%` : "--"}</p>
        </div>
      </div>
    </div>
  );
}

function BenchmarkRow({ comparison }: { comparison: BacktestComparison }) {
  return (
    <div className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm">
      <span className="font-medium">Buy &amp; hold {comparison.symbol}</span>
      <span>{formatPct(comparison.total_return_pct)}</span>
      <span className="text-muted-foreground">{formatPct(comparison.max_drawdown_pct)} max drawdown</span>
    </div>
  );
}

export function BacktestTab() {
  const { activeAgent, isLoading: agentLoading } = useActiveAgent();
  const [days, setDays] = useState(90);
  const runBacktest = useRunBacktest();

  if (agentLoading) {
    return <p className="text-muted-foreground">Loading...</p>;
  }

  if (!activeAgent) {
    return <p className="text-muted-foreground">Confirm a strategy first -- there's nothing to backtest yet.</p>;
  }

  function handleRun() {
    if (!activeAgent) return;
    runBacktest.mutate({ strategyId: activeAgent.id, days });
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 rounded-lg border border-border p-4">
        <label className="text-sm text-muted-foreground" htmlFor="backtest-days">
          Window (days)
        </label>
        <input
          id="backtest-days"
          type="number"
          min={1}
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="w-20 rounded-md border border-border bg-transparent px-2 py-1 text-sm"
        />
        <Button size="sm" onClick={handleRun} disabled={runBacktest.isPending}>
          {runBacktest.isPending ? "Running..." : "Run Backtest"}
        </Button>
      </div>

      <p className="text-xs text-muted-foreground">
        This is a historical simulation, not a prediction -- how these exact rules would have
        performed against real historical prices, not a forecast of future results.
      </p>

      {runBacktest.isError && (
        <p className="text-sm text-destructive">Something went wrong running the backtest. Try again.</p>
      )}

      {runBacktest.data && (
        <>
          <p className="text-sm text-muted-foreground">
            Starting capital basis: {runBacktest.data.capital_label}
          </p>

          <div className="space-y-3">
            {runBacktest.data.rules.map((metrics) => (
              <RuleMetricsCard key={metrics.symbol} metrics={metrics} />
            ))}
          </div>

          {runBacktest.data.benchmarks.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-sm font-medium text-muted-foreground">Benchmark (buy &amp; hold)</h4>
              {runBacktest.data.benchmarks.map((comparison) => (
                <BenchmarkRow key={comparison.symbol} comparison={comparison} />
              ))}
            </div>
          )}

          {runBacktest.data.limitations.length > 0 && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 text-sm text-amber-700 dark:text-amber-400">
              {runBacktest.data.limitations.map((limitation, i) => (
                <p key={i}>{limitation}</p>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}