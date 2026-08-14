"""FundamentalAnalystAgent: wraps get_fundamental_context (Finnhub).
Same thin-adapter template as every other Agent. Reports facts only --
never an interpretation, since there's no empirically-grounded
threshold (the way the AssetDirectory ambiguity threshold was actually
measured) for what counts as a "high" or "low" P/E ratio.

Distinguishes two different reasons for "I don't have that," rather
than collapsing them into one generic message:
- not configured at all (no Finnhub key set) -- an operational gap
- configured, but Finnhub has no data for this symbol -- a real,
  per-symbol data gap
"""

from app.agent.agent_contracts import AgentName, CapabilityResult, ClarificationRequest
from app.agent.context.fundamental_context import FinnhubClient, get_fundamental_context
from app.agent.pipeline.types import AgentExecutionContext


class FundamentalAnalystAgent:
    name = AgentName.FUNDAMENTAL_ANALYST

    def __init__(self, client: FinnhubClient | None) -> None:
        self._client = client

    def execute(self, context: AgentExecutionContext) -> list[CapabilityResult]:
        grounded = context.grounded_context

        if self._client is None:
            return [CapabilityResult(
                agent=self.name, description="Fundamental data isn't configured",
                facts=["I don't have a fundamentals data source configured right now."],
            )]

        if grounded.ambiguous_entities and not grounded.resolved_entities:
            candidates = [c for a in grounded.ambiguous_entities for c in a.candidates]
            return [CapabilityResult(
                agent=self.name, description="Asked which asset was meant before checking fundamentals",
                clarification=ClarificationRequest(
                    question_text=f"Which did you mean: {', '.join(candidates)}?", candidates=candidates,
                ),
            )]

        if not grounded.resolved_entities:
            return [CapabilityResult(
                agent=self.name, description="Nothing to check -- no asset was identified this turn",
                facts=["I'm not sure which company you're asking about."],
            )]

        results: list[CapabilityResult] = []
        for resolved in grounded.resolved_entities:
            symbol = resolved.entity.value
            fundamentals = get_fundamental_context(symbol, self._client)

            if fundamentals is None:
                results.append(CapabilityResult(
                    agent=self.name, description=f"No fundamentals data available for {symbol}",
                    facts=[f"I don't have fundamentals data for {symbol}."],
                    affected_entities=[resolved.entity],
                ))
                continue

            facts = []
            if fundamentals.company_name or fundamentals.sector:
                facts.append(
                    f"{fundamentals.company_name or symbol} is classified under "
                    f"{fundamentals.sector or 'an unspecified sector'}."
                )
            if fundamentals.market_cap is not None:
                facts.append(f"Market capitalization is approximately ${fundamentals.market_cap:,.0f} million.")
            if fundamentals.pe_ratio is not None:
                facts.append(f"P/E ratio (TTM) is {fundamentals.pe_ratio:.2f}.")
            if fundamentals.dividend_yield_pct is not None:
                facts.append(f"Dividend yield is approximately {fundamentals.dividend_yield_pct:.2f}%.")

            if not facts:
                facts = [f"I found {symbol} but Finnhub doesn't have detailed fundamentals for it."]

            results.append(CapabilityResult(
                agent=self.name, description=f"Reported fundamentals for {symbol}",
                facts=facts, affected_entities=[resolved.entity],
            ))
        return results