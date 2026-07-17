import { useNavigate } from "react-router-dom";
import { markOnboardingComplete } from "@/lib/onboarding";

export function TradingModePage() {
  const navigate = useNavigate();

  function handleSelectAgent() {
    markOnboardingComplete();
    navigate("/dashboard");
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center gap-8 py-24 text-center">
      <div>
        <h1 className="text-2xl font-semibold">How would you like to start?</h1>
        <p className="mt-2 text-muted-foreground">
          CapitalForge supports multiple ways to trade. You can add more
          later — this isn't a permanent choice.
        </p>
      </div>

      <div className="grid w-full gap-4 sm:grid-cols-2">
        <button
          onClick={handleSelectAgent}
          className="rounded-lg border border-border bg-background p-6 text-left transition-colors hover:bg-muted"
        >
          <h2 className="font-medium">AI Trading Agent</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Describe your trading rules in plain language. The agent
            executes them continuously on your paper account.
          </p>
        </button>

        <div className="cursor-not-allowed rounded-lg border border-border bg-muted/50 p-6 text-left opacity-60">
          <h2 className="font-medium">Manual Paper Trading</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Place trades yourself on your paper account.
          </p>
          <span className="mt-2 inline-block text-xs font-medium text-muted-foreground">
            Coming Soon
          </span>
        </div>
      </div>
    </div>
  );
}