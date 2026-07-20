import type { StrategyConfig } from "@/types/strategy";
import { formatAssetRule } from "@/lib/formatStrategy";

interface DraftPaneProps {
  draft: StrategyConfig | null | undefined;
}

export function DraftPane({ draft }: DraftPaneProps) {
  const hasAssets = draft && draft.asset_rules.length > 0;

  return (
    <div className="flex h-full flex-col rounded-lg border border-border">
      <div className="border-b border-border bg-muted/50 px-4 py-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Current Trading Rules
        </span>
      </div>
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {!hasAssets ? (
          <p className="text-sm text-muted-foreground">
            Your agent doesn't have any trading rules yet. Describe a rule in
            the chat to teach it.
          </p>
        ) : (
          draft!.asset_rules.map((rule) => {
            const formatted = formatAssetRule(rule);
            return (
              <div key={rule.symbol} className="rounded-md border border-border p-3">
                <h3 className="font-medium">{formatted.symbol}</h3>
                <dl className="mt-2 space-y-1 text-sm text-muted-foreground">
                  <div>
                    <dt className="inline font-medium text-foreground">Buy: </dt>
                    <dd className="inline">{formatted.buy}</dd>
                  </div>
                  <div>
                    <dt className="inline font-medium text-foreground">Sell: </dt>
                    <dd className="inline">{formatted.sell}</dd>
                  </div>
                  <div>
                    <dt className="inline font-medium text-foreground">Size: </dt>
                    <dd className="inline">{formatted.sizing}</dd>
                  </div>
                  {formatted.exit && (
                    <div>
                      <dt className="inline font-medium text-foreground">Exit: </dt>
                      <dd className="inline">{formatted.exit}</dd>
                    </div>
                  )}
                </dl>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}