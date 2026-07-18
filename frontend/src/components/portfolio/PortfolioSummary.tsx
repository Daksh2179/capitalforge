import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import type { PortfolioHoldingResponse } from "@/types/portfolio";

interface PortfolioSummaryProps {
  holdings: PortfolioHoldingResponse[];
}

export function PortfolioSummary({ holdings }: PortfolioSummaryProps) {
  const navigate = useNavigate();

  const total = holdings.length;
  const configuredCount = holdings.filter((h) => h.is_ai_configured).length;
  const needsSetupCount = total - configuredCount;

  const state: "empty" | "incomplete" | "ready" =
    total === 0 ? "empty" : needsSetupCount > 0 ? "incomplete" : "ready";

  function handlePrimaryAction() {
    if (state === "empty") {
      navigate("/markets");
      return;
    }

    const unconfiguredSymbols = holdings
      .filter((h) => !h.is_ai_configured)
      .map((h) => h.symbol);

    const message =
      state === "incomplete"
        ? `I'd like to configure trading rules for ${unconfiguredSymbols.join(", ")} from my portfolio.`
        : undefined;

    navigate("/agent", { state: message ? { prefillMessage: message } : undefined });
  }

  const buttonLabel =
    state === "empty" ? "Browse Markets" : state === "incomplete" ? "Configure in AI Agent" : "Open AI Agent";

  return (
    <div className="mb-8 rounded-lg border border-border bg-muted/30 p-6">
      <p className="mb-4 text-sm text-muted-foreground">
        The user builds the portfolio. The AI manages the portfolio.
      </p>

      {total > 0 && (
        <p className="mb-2 text-lg font-medium">
          {total} {total === 1 ? "Holding" : "Holdings"}
        </p>
      )}

      {total > 0 && (
        <p className="mb-4 text-sm text-muted-foreground">
          {configuredCount} Agent Assigned • {needsSetupCount} Need Setup
        </p>
      )}

      <p className="mb-4 text-sm font-medium">
        {state === "empty" && "No holdings yet — start by browsing Markets."}
        {state === "incomplete" && "⚠ Incomplete — some holdings still need AI configuration."}
        {state === "ready" && "✅ Ready — every holding has an assigned agent."}
      </p>

      <Button onClick={handlePrimaryAction}>{buttonLabel}</Button>
    </div>
  );
}