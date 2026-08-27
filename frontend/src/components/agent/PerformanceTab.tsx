import { useNavigate } from "react-router-dom";
import { useActiveAgent } from "@/hooks/useActiveAgent";
import { useDecisionLogs } from "@/hooks/useDecisionLogs";
import { computeOpportunityStats } from "@/lib/computeOpportunityStats";
import { Button } from "@/components/ui/button";

export function PerformanceTab() {
  const navigate = useNavigate();
  const { activeAgent, isLoading: agentLoading } = useActiveAgent();
  // A wider sample than History's default -- this tab summarizes
  // trends, not recent individual events.
  const { data: logs, isLoading: logsLoading } = useDecisionLogs(activeAgent?.id ?? null, 200);

  if (agentLoading || logsLoading) {
    return <p className="text-muted-foreground">Loading strategy health...</p>;
  }

  if (!activeAgent) {
    return (
      <p className="text-muted-foreground">
        Confirm a strategy first -- health metrics build up as it evaluates.
      </p>
    );
  }

  const stats = computeOpportunityStats(logs ?? []);

  function askAboutPerformance() {
    navigate("/agent", {
      state: { prefillMessage: "How has my strategy performed so far, including drawdown?" },
    });
  }

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-border p-6">
        <h3 className="mb-3 text-sm font-medium text-muted-foreground">
          Buy Opportunities ({stats.totalEvaluated} evaluated)
        </h3>
        {stats.totalEvaluated === 0 ? (
          <p className="text-sm text-muted-foreground">
            No buy conditions have triggered yet -- this fills in as your strategy runs.
          </p>
        ) : (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div>
              <p className="text-xs text-muted-foreground">Executed</p>
              <p className="text-lg font-semibold text-emerald-600 dark:text-emerald-400">{stats.executed}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Rejected by Risk</p>
              <p className="text-lg font-semibold text-destructive">{stats.rejectedByRisk}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Deferred</p>
              <p className="text-lg font-semibold text-amber-600 dark:text-amber-400">{stats.deferred}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Skipped</p>
              <p className="text-lg font-semibold text-muted-foreground">
                {stats.skippedLiquidity + stats.skippedPaused}
              </p>
            </div>
          </div>
        )}
        <p className="mt-3 text-xs text-muted-foreground">
          "Deferred" means another candidate won the same cycle's capital competition. "Skipped"
          covers insufficient liquidity or the strategy being paused at the time.
        </p>
      </div>

      <div className="rounded-lg border border-border p-6">
        <h3 className="mb-2 text-sm font-medium text-muted-foreground">Return &amp; Drawdown</h3>
        <p className="mb-3 text-sm text-muted-foreground">
          These numbers come from your Performance Analyst Agent, computed from real portfolio
          history -- ask it directly for the current figures.
        </p>
        <Button variant="outline" size="sm" onClick={askAboutPerformance}>
          Ask AI Agent
        </Button>
      </div>
    </div>
  );
}