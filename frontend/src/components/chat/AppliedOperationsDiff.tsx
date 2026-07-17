import type { AppliedOperation } from "@/types/agent";

interface AppliedOperationsDiffProps {
  operations: AppliedOperation[];
}

export function AppliedOperationsDiff({ operations }: AppliedOperationsDiffProps) {
  if (operations.length === 0) return null;

  return (
    <div className="rounded-md border border-border bg-muted/50 px-3 py-2 text-xs">
      {operations.map((op, i) => (
        <div key={i} className="text-muted-foreground">
          {op.symbol ? `${op.symbol}: ` : ""}
          {op.description}
        </div>
      ))}
    </div>
  );
}