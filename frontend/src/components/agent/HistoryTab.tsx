import { useActiveAgent } from "@/hooks/useActiveAgent";
import { useDecisionLogs } from "@/hooks/useDecisionLogs";
import {
  formatActionTaken,
  formatPlanOutcome,
  getLogSymbol,
  getOutcomeColor,
} from "@/lib/formatDecisionLog";

export function HistoryTab() {
  const { activeAgent, isLoading: agentLoading } = useActiveAgent();
  const { data: logs, isLoading: logsLoading } = useDecisionLogs(activeAgent?.id ?? null, 100);

  if (agentLoading || logsLoading) {
    return <p className="text-muted-foreground">Loading decision history...</p>;
  }

  if (!activeAgent) {
    return (
      <p className="text-muted-foreground">
        Your agent hasn't evaluated anything yet -- decision history will
        appear here once it's active.
      </p>
    );
  }

  if (!logs || logs.length === 0) {
    return <p className="text-muted-foreground">No decisions recorded yet.</p>;
  }

  return (
    <div className="space-y-3">
      {logs.map((log) => {
        const planOutcomeLabel = formatPlanOutcome(log.plan_outcome);
        return (
          <div key={log.id} className="rounded-lg border border-border p-4">
            <div className="flex items-center justify-between">
              <span className="font-medium">{getLogSymbol(log)}</span>
              <span className="text-xs text-muted-foreground">
                {new Date(log.timestamp).toLocaleString()}
              </span>
            </div>

            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm">
              <span className={getOutcomeColor(log)}>{formatActionTaken(log.action_taken)}</span>
              {planOutcomeLabel && (
                <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                  {planOutcomeLabel}
                </span>
              )}
            </div>

            {log.explanation_text ? (
              <p className="mt-2 text-sm text-muted-foreground">{log.explanation_text}</p>
            ) : (
              <p className="mt-2 text-sm text-muted-foreground">{log.risk_reason}</p>
            )}

            {log.rules_triggered_json.length > 0 && (
              <p className="mt-1 text-xs text-muted-foreground">
                Rules: {log.rules_triggered_json.join(", ")}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}