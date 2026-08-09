"""MarketResearchAgent: wraps the existing get_market_context. Same
'thin adapter over an existing service' template as
StrategyBuilderAgent, but simpler -- no legacy ConversationState to
carry through, since this Agent consumes GroundedContext directly, the
real contract every future Agent gets.

Reports facts only (current price, 52-week range) -- never an
interpretation. That boundary is deliberate and structural: conventional
interpretation of a number belongs to TechnicalAnalystAgent, not here.
Market Research's domain is "what is true," not "what it conventionally
means."

What this Agent is explicitly not allowed to infer: it never predicts
future price, and it never reports on fundamentals/news -- those
belong to FundamentalAnalystAgent, a separate, not-yet-implemented
roster entry. Silence on fundamentals here is deliberate, not an
oversight -- the pipeline's own "not implemented yet" step for
FundamentalAnalystAgent is what should speak to that gap, not this
Agent pretending to cover it.
"""

from app.agent.agent_contracts import AgentName, CapabilityResult, ClarificationRequest
from app.agent.context.market_context import get_market_context
from app.agent.pipeline.types import GroundedContext
from app.trading_engine.market_data.provider import MarketDataProvider


class MarketResearchAgent:
    name = AgentName.MARKET_RESEARCH

    def __init__(self, market_data: MarketDataProvider) -> None:
        self._market_data = market_data

    def execute(self, context: GroundedContext) -> list[CapabilityResult]:
        if context.ambiguous_entities and not context.resolved_entities:
            candidates = [c for a in context.ambiguous_entities for c in a.candidates]
            first = context.ambiguous_entities[0]
            return [CapabilityResult(
                agent=self.name,
                description=f"Asked which asset was meant for {first.raw_text!r}",
                clarification=ClarificationRequest(
                    question_text=f"Which did you mean: {', '.join(candidates)}?",
                    candidates=candidates,
                ),
            )]

        if not context.resolved_entities:
            if context.unresolved_entities:
                names = ", ".join(e.raw_text for e in context.unresolved_entities)
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
        for resolved in context.resolved_entities:
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