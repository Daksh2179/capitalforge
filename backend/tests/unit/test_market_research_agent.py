"""Unit tests for MarketResearchAgent, exercised directly against
GroundedContext -- not yet wired into ConversationPipeline (that's a
separate, deliberate step, matching how StrategyBuilderAgent was
validated standalone before being wired in)."""

from datetime import datetime, timedelta, timezone

from app.agent.agents.market_research_agent import MarketResearchAgent
from app.agent.conversation_memory import EntityReference
from app.agent.pipeline.types import (
    AmbiguityReason,
    AmbiguousEntity,
    GoalExtractionIntent,
    GroundedContext,
    ResolvedEntity,
    UnresolvedEntity,
)
from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.market_data.provider import MarketDataProvider


class FakeMarketDataProvider(MarketDataProvider):
    def __init__(self, bars_by_symbol: dict[str, list[MarketBar]]) -> None:
        self._bars_by_symbol = bars_by_symbol

    def get_historical_bars(self, symbol, timeframe, start, end):
        return self._bars_by_symbol.get(symbol, [])


def _bars(symbol: str, closes: list[float]) -> list[MarketBar]:
    base = datetime.now(timezone.utc) - timedelta(days=len(closes))
    return [
        MarketBar(symbol=symbol, timestamp=base + timedelta(days=i),
                  open=c, high=c + 5, low=c - 5, close=c, volume=100_000.0)
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
    ambiguous_entities: list | None = None,
    unresolved_entities: list | None = None,
) -> GroundedContext:
    return GroundedContext(
        intent=intent,
        goal_relation=None,
        goal_summary=None,
        resolved_entities=resolved_entities or [],
        ambiguous_entities=ambiguous_entities or [],
        unresolved_entities=unresolved_entities or [],
        raw_message="x",
    )


def test_reports_price_and_52_week_range_for_a_resolved_symbol():
    market_data = FakeMarketDataProvider({"NVDA": _bars("NVDA", [100.0 + i for i in range(30)])})
    agent = MarketResearchAgent(market_data)
    context = _context(resolved_entities=[_resolved("NVDA")])

    results = agent.execute(context)

    assert len(results) == 1
    assert "NVDA" in results[0].facts[0]
    assert results[0].interpretation is None
    assert results[0].affected_entities[0].value == "NVDA"


def test_no_data_for_symbol_reports_honest_limitation_not_error():
    agent = MarketResearchAgent(FakeMarketDataProvider({}))
    context = _context(resolved_entities=[_resolved("NVDA")])

    results = agent.execute(context)

    assert len(results) == 1
    assert "don't have" in results[0].facts[0]
    assert results[0].draft_change is None


def test_ambiguous_entity_raises_clarification_instead_of_guessing():
    agent = MarketResearchAgent(FakeMarketDataProvider({}))
    context = _context(
        resolved_entities=[],
        ambiguous_entities=[AmbiguousEntity(
            raw_text="Alphabet", reason=AmbiguityReason.MULTIPLE_CLOSE_MATCHES,
            candidates=["GOOGL", "GOOG"], explanation="near tie",
        )],
    )

    results = agent.execute(context)

    assert len(results) == 1
    assert results[0].clarification is not None
    assert set(results[0].clarification.candidates) == {"GOOGL", "GOOG"}


def test_unresolved_entity_reports_no_match_not_silence():
    agent = MarketResearchAgent(FakeMarketDataProvider({}))
    context = _context(
        resolved_entities=[],
        unresolved_entities=[UnresolvedEntity(raw_text="Nonexistent Corp", explanation="no match")],
    )

    results = agent.execute(context)

    assert len(results) == 1
    assert "Nonexistent Corp" in results[0].description


def test_nothing_resolved_at_all_reports_honest_gap():
    agent = MarketResearchAgent(FakeMarketDataProvider({}))
    context = _context(resolved_entities=[])

    results = agent.execute(context)

    assert len(results) == 1
    assert "not sure which company" in results[0].facts[0]


def test_multiple_resolved_entities_each_get_their_own_result():
    market_data = FakeMarketDataProvider({
        "NVDA": _bars("NVDA", [100.0 + i for i in range(30)]),
        "AMD": _bars("AMD", [50.0 + i for i in range(30)]),
    })
    agent = MarketResearchAgent(market_data)
    context = _context(resolved_entities=[_resolved("NVDA"), _resolved("AMD")])

    results = agent.execute(context)

    assert len(results) == 2
    symbols = {r.affected_entities[0].value for r in results}
    assert symbols == {"NVDA", "AMD"}