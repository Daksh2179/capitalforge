"""Unit tests for TechnicalAnalystAgent."""

from datetime import datetime, timedelta, timezone

from app.agent.agents.technical_analyst_agent import TechnicalAnalystAgent
from app.agent.conversation_memory import ConceptReference, ConversationMemory, EntityReference
from app.agent.pipeline.types import (
    AgentExecutionContext,
    AmbiguityReason,
    AmbiguousEntity,
    GoalExtractionIntent,
    GroundedContext,
    ResolvedEntity,
)
from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.market_data.provider import MarketDataProvider


class FakeMarketDataProvider(MarketDataProvider):
    def __init__(self, bars_by_symbol: dict[str, list[MarketBar]]) -> None:
        self._bars_by_symbol = bars_by_symbol

    def get_historical_bars(self, symbol, timeframe, start, end):
        return self._bars_by_symbol.get(symbol, [])


def _bars(closes: list[float]) -> list[MarketBar]:
    base = datetime.now(timezone.utc) - timedelta(days=len(closes))
    return [
        MarketBar(symbol="TEST", timestamp=base + timedelta(days=i),
                  open=c, high=c, low=c, close=c, volume=100_000.0)
        for i, c in enumerate(closes)
    ]


def _resolved(symbol: str) -> ResolvedEntity:
    return ResolvedEntity(
        raw_text=symbol,
        entity=EntityReference(kind="symbol", value=symbol, display_name=f"{symbol} Inc. ({symbol})"),
        explanation="test fixture",
    )


def _context(
    intent: GoalExtractionIntent = GoalExtractionIntent.RESEARCH,
    resolved_entities: list | None = None,
    resolved_concepts: list | None = None,
    ambiguous_entities: list | None = None,
    unresolved_entities: list | None = None,
) -> AgentExecutionContext:
    grounded = GroundedContext(
        intent=intent,
        goal_relation=None,
        goal_summary=None,
        resolved_entities=resolved_entities or [],
        resolved_concepts=resolved_concepts or [],
        ambiguous_entities=ambiguous_entities or [],
        unresolved_entities=unresolved_entities or [],
        raw_message="x",
    )
    return AgentExecutionContext(grounded_context=grounded, memory=ConversationMemory())


def test_explicit_rsi_request_computes_only_rsi():
    descending = [130.0 - i for i in range(30)]
    market_data = FakeMarketDataProvider({"NVDA": _bars(descending)})
    agent = TechnicalAnalystAgent(market_data)
    context = _context(
        resolved_entities=[_resolved("NVDA")],
        resolved_concepts=[ConceptReference(name="RSI", introduced_by="grounding")],
    )

    results = agent.execute(context)

    assert len(results) == 1
    assert len(results[0].facts) == 1
    assert "RSI" in results[0].facts[0]
    assert "oversold" in results[0].interpretation
    assert "not predictions" in results[0].interpretation


def test_generic_technicals_request_computes_the_v1_snapshot():
    bars = _bars([100.0 + (i % 5) for i in range(220)])
    market_data = FakeMarketDataProvider({"NVDA": bars})
    agent = TechnicalAnalystAgent(market_data)
    context = _context(resolved_entities=[_resolved("NVDA")], resolved_concepts=[])

    results = agent.execute(context)

    assert len(results) == 1
    indicators_mentioned = " ".join(results[0].facts)
    assert "RSI(14)" in indicators_mentioned
    assert "SMA(50)" in indicators_mentioned
    assert "SMA(200)" in indicators_mentioned


def test_facts_and_interpretation_are_kept_in_separate_fields():
    descending = [130.0 - i for i in range(30)]
    market_data = FakeMarketDataProvider({"NVDA": _bars(descending)})
    agent = TechnicalAnalystAgent(market_data)
    context = _context(
        resolved_entities=[_resolved("NVDA")],
        resolved_concepts=[ConceptReference(name="RSI", introduced_by="grounding")],
    )

    results = agent.execute(context)

    assert results[0].facts[0] != results[0].interpretation
    assert "oversold" not in results[0].facts[0]


def test_ambiguous_entity_raises_clarification_instead_of_guessing():
    agent = TechnicalAnalystAgent(FakeMarketDataProvider({}))
    context = _context(
        resolved_entities=[],
        ambiguous_entities=[AmbiguousEntity(
            raw_text="Alphabet", reason=AmbiguityReason.MULTIPLE_CLOSE_MATCHES,
            candidates=["GOOGL", "GOOG"], explanation="near tie",
        )],
    )

    results = agent.execute(context)

    assert results[0].clarification is not None
    assert set(results[0].clarification.candidates) == {"GOOGL", "GOOG"}


def test_nothing_resolved_reports_honest_gap():
    agent = TechnicalAnalystAgent(FakeMarketDataProvider({}))
    context = _context(resolved_entities=[])

    results = agent.execute(context)

    assert "not sure which company" in results[0].facts[0]


def test_no_data_reports_honest_limitation():
    agent = TechnicalAnalystAgent(FakeMarketDataProvider({}))
    context = _context(
        resolved_entities=[_resolved("NVDA")],
        resolved_concepts=[ConceptReference(name="RSI", introduced_by="grounding")],
    )

    results = agent.execute(context)

    assert "don't have enough" in results[0].facts[0]