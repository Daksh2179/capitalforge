"""TechnicalAnalystAgent: wraps get_indicator_readings, which itself
wraps the existing indicator registry -- never a second computation.

Reports fact -> conventional interpretation -> explicit limit, in that
order, with facts and interpretation kept in separate CapabilityResult
fields.

Two request shapes: an explicit named indicator computes only that;
a generic technicals request computes the documented V1 snapshot --
RSI(14), SMA(50), SMA(200).

What this Agent is explicitly not allowed to infer: never predicts a
future indicator reading or price; never asserts a conventional
reading implies a trade should happen -- that boundary belongs to
InvestmentAnalystAgent, and only on an EVALUATE-classified turn.
"""

from app.agent.agent_contracts import AgentName, CapabilityResult, ClarificationRequest
from app.agent.context.indicator_context import IndicatorReading, get_indicator_readings
from app.agent.conversation_memory import ConceptReference
from app.agent.pipeline.types import AgentExecutionContext
from app.trading_engine.market_data.provider import MarketDataProvider

_SNAPSHOT_REQUESTS: list[tuple[str, int]] = [("RSI", 14), ("SMA", 50), ("SMA", 200)]

_DEFAULT_PERIODS: dict[str, int] = {"RSI": 14, "SMA": 50, "EMA": 20}

_LIMIT_NOTE = "These are conventional technical readings, not predictions of future price movement."


def _interpret(reading: IndicatorReading, current_price: float | None) -> str:
    if reading.indicator == "RSI":
        if reading.value < 30:
            return f"RSI({reading.period}) below 30 is conventionally read as oversold."
        if reading.value > 70:
            return f"RSI({reading.period}) above 70 is conventionally read as overbought."
        return f"RSI({reading.period}) is in the neutral range by conventional readings."
    if reading.indicator in ("SMA", "EMA") and current_price is not None:
        relation = "above" if current_price > reading.value else "below"
        return f"Price is currently {relation} the {reading.period}-period {reading.indicator}."
    return f"{reading.indicator}({reading.period}) is {reading.value:.2f}."


class TechnicalAnalystAgent:
    name = AgentName.TECHNICAL_ANALYST

    def __init__(self, market_data: MarketDataProvider) -> None:
        self._market_data = market_data

    def execute(self, context: AgentExecutionContext) -> list[CapabilityResult]:
        grounded = context.grounded_context

        if grounded.ambiguous_entities and not grounded.resolved_entities:
            candidates = [c for a in grounded.ambiguous_entities for c in a.candidates]
            return [CapabilityResult(
                agent=self.name, description="Asked which asset was meant before computing indicators",
                clarification=ClarificationRequest(
                    question_text=f"Which did you mean: {', '.join(candidates)}?", candidates=candidates,
                ),
            )]

        if not grounded.resolved_entities:
            return [CapabilityResult(
                agent=self.name, description="Nothing to analyze -- no asset was identified this turn",
                facts=["I'm not sure which company you're asking about."],
            )]

        requests = self._build_requests(grounded)
        needs_price_reference = any(name in ("SMA", "EMA") for name, _ in requests)

        results: list[CapabilityResult] = []
        for resolved in grounded.resolved_entities:
            symbol = resolved.entity.value
            fetch_requests = [*requests, ("PRICE", 1)] if needs_price_reference else requests
            readings = get_indicator_readings(symbol, self._market_data, fetch_requests)

            current_price = next((r.value for r in readings if r.indicator == "PRICE"), None)
            display_readings = [r for r in readings if r.indicator != "PRICE"]

            if not display_readings:
                results.append(CapabilityResult(
                    agent=self.name, description=f"No indicator data available for {symbol}",
                    facts=[f"I don't have enough recent data to compute technicals for {symbol}."],
                    affected_entities=[resolved.entity],
                ))
                continue

            facts = [f"{symbol}'s {r.indicator}({r.period}) is {r.value:.2f}." for r in display_readings]
            interpretations = [_interpret(r, current_price) for r in display_readings]

            # Only RSI has an established conventional threshold (30/70)
            # we can point to -- no invented threshold for SMA/EMA
            # position, so evidence_signal stays None unless RSI ran.
            rsi_readings = [r for r in display_readings if r.indicator == "RSI"]
            evidence_signal = None
            if rsi_readings:
                rsi_value = rsi_readings[0].value
                if rsi_value < 30:
                    evidence_signal = "supportive"
                elif rsi_value > 70:
                    evidence_signal = "concerning"
                else:
                    evidence_signal = "neutral"

            results.append(CapabilityResult(
                agent=self.name,
                description=f"Computed {', '.join(r.indicator for r in display_readings)} for {symbol}",
                facts=facts,
                interpretation=" ".join(interpretations) + " " + _LIMIT_NOTE,
                affected_entities=[resolved.entity],
                introduced_concepts=[
                    ConceptReference(name=r.indicator, introduced_by=self.name.value) for r in display_readings
                ],
                evidence_signal=evidence_signal,
            ))
        return results

    def _build_requests(self, grounded) -> list[tuple[str, int]]:
        explicit = [c for c in grounded.resolved_concepts if c.name in _DEFAULT_PERIODS]
        if explicit:
            return [(c.name, _DEFAULT_PERIODS[c.name]) for c in explicit]
        return _SNAPSHOT_REQUESTS