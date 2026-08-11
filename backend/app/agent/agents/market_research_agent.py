"""MarketResearchAgent: wraps the existing get_market_context. Same
'thin adapter over an existing service' template as StrategyBuilderAgent,
but simpler -- no legacy ConversationState to carry through.

Reports facts only (current price, 52-week range) -- never an
interpretation. That boundary is deliberate and structural: conventional
interpretation of a number belongs to TechnicalAnalystAgent, not here.

What this Agent is explicitly not allowed to infer: it never predicts
future price, and it never reports on fundamentals/news -- those
belong to FundamentalAnalystAgent, a separate, not-yet-implemented
roster entry.
"""

from app.agent.agent_contracts import AgentName, CapabilityResult, ClarificationRequest
from app.agent.context.market_context import get_market_context
from app.agent.pipeline.types import AgentExecutionContext
from app.trading_engine.market_data.provider import MarketDataProvider


class MarketResearchAgent:
    name = AgentName.MARKET_RESEARCH

    def __init__(self, market_data: MarketDataProvider) -> None:
        self._market_data = market_data

    def execute(self, context: AgentExecutionContext) -> list[CapabilityResult]:
        grounded = context.grounded_context

        if grounded.ambiguous_entities and not grounded.resolved_entities:
            candidates = [c for a in grounded.ambiguous_entities for c in a.candidates]
            first = grounded.ambiguous_entities[0]
            return [CapabilityResult(
                agent=self.name,
                description=f"Asked which asset was meant for {first.raw_text!r}",
                clarification=ClarificationRequest(
                    question_text=f"Which did you mean: {', '.join(candidates)}?",
                    candidates=candidates,
                ),
            )]

        if not grounded.resolved_entities:
            if grounded.unresolved_entities:
                names = ", ".join(e.raw_text for e in grounded.unresolved_entities)
                return [CapabilityResult(
                    agent=self.name, description=f"No match found for {names}",
                    facts=[f"I couldn't find a tradable match for {names}."],
                )]
            return [CapabilityResult(
                agent=self.name,
                description="Nothing to research -- no asset was identified this turn",
                facts=["I'm not sure which company you're asking about."],
            )]

        results: list[CapabilityResult] = []
        for resolved in grounded.resolved_entities:
            symbol = resolved.entity.value
            market_context = get_market_context(symbol, self._market_data)

            if market_context is None:
                results.append(CapabilityResult(
                    agent=self.name, description=f"No recent market data available for {symbol}",
                    facts=[f"I don't have recent price data for {symbol} right now."],
                    affected_entities=[resolved.entity],
                ))
                continue

            fact = (
                f"{market_context.symbol} is trading around ${market_context.current_price:.2f}, "
                f"with a 52-week range of ${market_context.week_52_low:.2f}"
                f"-${market_context.week_52_high:.2f}."
            )
            results.append(CapabilityResult(
                agent=self.name, description=f"Reported current price and 52-week range for {symbol}",
                facts=[fact], affected_entities=[resolved.entity],
            ))

        return results