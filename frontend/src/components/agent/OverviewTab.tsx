import { useActiveAgent } from "@/hooks/useActiveAgent";
import { useCurrentVersion } from "@/hooks/useCurrentVersion";
import { useDecisionLogs } from "@/hooks/useDecisionLogs";
import { usePauseStrategy, useResumeStrategy } from "@/hooks/useStrategyActions";
import { formatPortfolioRules } from "@/lib/formatStrategy";
import { Button } from "@/components/ui/button";

export function OverviewTab() {
  const { activeAgent, isLoading: agentLoading } = useActiveAgent();
  const { data: currentVersion } = useCurrentVersion(activeAgent?.id ?? null);
  const { data: logs, isLoading: logsLoading } = useDecisionLogs(activeAgent?.id ?? null, 20);

  // Both mutations must be called unconditionally, before any early
  // return below -- calling hooks after a conditional return violates
  // the Rules of Hooks and would throw as soon as activeAgent is null.
  const pauseStrategyMutation = usePauseStrategy();
  const resumeStrategyMutation = useResumeStrategy();

  if (agentLoading) {
    return <p className="text-muted-foreground">Loading agent status...</p>;
  }

  if (!activeAgent) {
    return (
      <div className="rounded-lg border border-border p-6 text-center">
        <p className="text-muted-foreground">
          Your agent doesn't have any active trading rules yet. Head to Chat
          to teach it how to manage your portfolio.
        </p>
      </div>
    );
  }

  const symbols = currentVersion?.config_json.asset_rules.map((r) => r.symbol) ?? [];

  const lastExecutedTrade = logs?.find((log) => log.action_taken !== "hold");
  const lastDecision = logs?.[0];

  const statusLabel =
    activeAgent.state === "active" ? "Running" : activeAgent.state === "paused" ? "Paused" : "Confirmed";

  const statusColor =
    activeAgent.state === "active"
      ? "text-emerald-600 dark:text-emerald-400"
      : activeAgent.state === "paused"
        ? "text-amber-600 dark:text-amber-400"
        : "text-muted-foreground";

  const canPause = activeAgent.state === "active";
  const canResume = activeAgent.state === "paused";
  const isMutating = pauseStrategyMutation.isPending || resumeStrategyMutation.isPending;

  function handlePauseResume() {
    if (!activeAgent) return;
    if (canPause) pauseStrategyMutation.mutate(activeAgent.id);
    else if (canResume) resumeStrategyMutation.mutate(activeAgent.id);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between rounded-lg border border-border p-6">
        <span className={`text-lg font-semibold ${statusColor}`}>{statusLabel}</span>
        {(canPause || canResume) && (
          <Button variant="outline" size="sm" onClick={handlePauseResume} disabled={isMutating}>
            {isMutating ? "Working..." : canPause ? "Pause" : "Resume"}
          </Button>
        )}
      </div>

      {activeAgent.state === "paused" && (
        <p className="-mt-4 text-xs text-muted-foreground">
          Existing positions are still protected (stop-loss/take-profit/sell conditions keep
          running) -- only new buys are suspended while paused.
        </p>
      )}

      <div className="rounded-lg border border-border p-6">
        <h3 className="mb-2 text-sm font-medium text-muted-foreground">Managing</h3>
        {symbols.length === 0 ? (
          <p className="text-sm text-muted-foreground">No symbols configured yet.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {symbols.map((symbol) => (
              <span
                key={symbol}
                className="rounded-full bg-muted px-3 py-1 text-sm font-medium"
              >
                {symbol}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-lg border border-border p-6">
        <h3 className="mb-2 text-sm font-medium text-muted-foreground">Portfolio Rules</h3>
        {!currentVersion ? (
          <p className="text-sm text-muted-foreground">No rules configured yet.</p>
        ) : (
          (() => {
            const formatted = formatPortfolioRules(currentVersion.config_json.portfolio_rules);
            return (
              <dl className="space-y-1 text-sm text-muted-foreground">
                <div>
                  <dt className="inline font-medium text-foreground">Trading pool: </dt>
                  <dd className="inline">{formatted.tradingPool}</dd>
                </div>
                <div>
                  <dt className="inline font-medium text-foreground">Cash reserve: </dt>
                  <dd className="inline">{formatted.cashReserve}</dd>
                </div>
                <div>
                  <dt className="inline font-medium text-foreground">Max per position: </dt>
                  <dd className="inline">{formatted.maxAllocation}</dd>
                </div>
                <div>
                  <dt className="inline font-medium text-foreground">Open positions: </dt>
                  <dd className="inline">{formatted.maxOpenPositions}</dd>
                </div>
              </dl>
            );
          })()
        )}
      </div>

      <div className="rounded-lg border border-border p-6">
        <h3 className="mb-2 text-sm font-medium text-muted-foreground">Last Decision</h3>
        {logsLoading && <p className="text-sm text-muted-foreground">Loading...</p>}
        {!logsLoading && !lastDecision && (
          <p className="text-sm text-muted-foreground">No decisions recorded yet.</p>
        )}
        {lastDecision && (
          <p className="text-sm">
            {lastDecision.explanation_text ?? `Action: ${lastDecision.action_taken}`}
          </p>
        )}
      </div>

      <div className="rounded-lg border border-border p-6">
        <h3 className="mb-2 text-sm font-medium text-muted-foreground">Last Executed Trade</h3>
        {logsLoading && <p className="text-sm text-muted-foreground">Loading...</p>}
        {!logsLoading && !lastExecutedTrade && (
          <p className="text-sm text-muted-foreground">No trades executed yet.</p>
        )}
        {lastExecutedTrade && (
          <p className="text-sm">
            {lastExecutedTrade.explanation_text ?? `Action: ${lastExecutedTrade.action_taken}`}
          </p>
        )}
      </div>
    </div>
  );
}