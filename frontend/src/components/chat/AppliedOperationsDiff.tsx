import type { AppliedOperation } from "@/types/agent";

interface AppliedOperationsDiffProps {
  operations: AppliedOperation[];
}

export function AppliedOperationsDiff({ operations }: AppliedOperationsDiffProps) {
  if (operations.length === 0) return null;

  return (
    <div className="rounded-md border border-border bg-muted/50 px-3 py-2 text-xs">
      {operations.map((op, i) => (
        <div key={i} className={i > 0 ? "mt-2" : ""}>
          <div className="text-muted-foreground">
            {op.symbol ? `${op.symbol}: ` : ""}
            {op.description}
          </div>
          {/* Only ever populated today for a brand-new rule's
              capital_allocation silently defaulting to 5% -- see
              draft_updater.py. Genuinely optional, not every op has one. */}
          {op.reasoning && (
            <div className="mt-0.5 italic text-muted-foreground/70">{op.reasoning}</div>
          )}
        </div>
      ))}
    </div>
  );
}