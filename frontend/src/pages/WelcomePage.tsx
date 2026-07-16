import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";

export function WelcomePage() {
  const navigate = useNavigate();

  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center gap-6 py-24 text-center">
      <h1 className="text-3xl font-semibold">Welcome to CapitalForge</h1>
      <p className="text-muted-foreground">
        CapitalForge is an AI Trading Agent for paper trading. You define
        the rules, in plain language or trading terminology, and the agent
        continuously executes them until you edit, pause, or stop it.
      </p>
      <Button onClick={() => navigate("/trading-mode")}>Get Started</Button>
    </div>
  );
}