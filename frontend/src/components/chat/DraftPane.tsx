import type { StrategyConfig } from "@/types/strategy";
import { formatAssetRule } from "@/lib/formatStrategy";

interface DraftPaneProps {
  draft: StrategyConfig | null | undefined;
}

export function DraftPane({ draft }: DraftPaneProps) {
  const hasAssets = draft && draft.asset_rules.length > 0;

  return (
    <div className="flex h-full flex-col rounded-lg border border-border">
      <div className="border-b border-border bg-amber-50 px-4 py-2 dark:bg-amber-950">
        <span className="text-xs font-semibold uppercase tracking-wide text-amber-800 dark:text-amber-300">
          Draft — not yet running
        </span>
      </div>
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {!hasAssets ? (
          <p className="text-sm text-muted-foreground">
            Nothing configured yet. Describe a rule in the chat to begin.
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