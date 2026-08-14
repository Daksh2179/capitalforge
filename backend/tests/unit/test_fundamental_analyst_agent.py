"""Unit tests for FundamentalAnalystAgent."""

from app.agent.agents.fundamental_analyst_agent import FundamentalAnalystAgent
from app.agent.conversation_memory import ConversationMemory, EntityReference
from app.agent.pipeline.types import (
    AgentExecutionContext,
    AmbiguityReason,
    AmbiguousEntity,
    GoalExtractionIntent,
    GroundedContext,
    ResolvedEntity,
)


class FakeFinnhubClient:
    def __init__(self, profile: dict, metrics: dict | None = None) -> None:
        self._profile = profile
        self._metrics = metrics or {}

    def get_profile(self, symbol: str) -> dict:
        return self._profile

    def get_metrics(self, symbol: str) -> dict:
        return self._metrics


def _resolved(symbol: str) -> ResolvedEntity:
    return ResolvedEntity(
        raw_text=symbol, entity=EntityReference(kind="symbol", value=symbol, display_name=symbol),
        explanation="test fixture",
    )


def _context(
    resolved_entities: list | None = None,
    ambiguous_entities: list | None = None,
) -> AgentExecutionContext:
    grounded = GroundedContext(
        intent=GoalExtractionIntent.RESEARCH, goal_relation=None, goal_summary=None,
        resolved_entities=resolved_entities or [], ambiguous_entities=ambiguous_entities or [], raw_message="x",
    )
    return AgentExecutionContext(grounded_context=grounded, memory=ConversationMemory())


def test_no_client_reports_not_configured():
    agent = FundamentalAnalystAgent(client=None)
    results = agent.execute(_context(resolved_entities=[_resolved("AAPL")]))

    assert "configured" in results[0].facts[0]


def test_reports_real_fundamentals_when_available():
    client = FakeFinnhubClient(
        profile={"name": "Apple Inc", "finnhubIndustry": "Technology Hardware", "marketCapitalization": 2800000.0},
        metrics={"metric": {"peBasicExclExtraTTM": 32.1, "dividendYieldIndicatedAnnual": 0.45}},
    )
    agent = FundamentalAnalystAgent(client)
    results = agent.execute(_context(resolved_entities=[_resolved("AAPL")]))

    facts_text = " ".join(results[0].facts)
    assert "Apple Inc" in facts_text
    assert "32.1" in facts_text


def test_no_data_for_symbol_reports_honest_gap():
    client = FakeFinnhubClient(profile={})
    agent = FundamentalAnalystAgent(client)
    results = agent.execute(_context(resolved_entities=[_resolved("NONEXISTENT")]))

    assert "don't have fundamentals data" in results[0].facts[0]


def test_ambiguous_entity_raises_clarification():
    agent = FundamentalAnalystAgent(FakeFinnhubClient(profile={}))
    results = agent.execute(_context(
        ambiguous_entities=[AmbiguousEntity(
            raw_text="Alphabet", reason=AmbiguityReason.MULTIPLE_CLOSE_MATCHES,
            candidates=["GOOGL", "GOOG"], explanation="near tie",
        )],
    ))

    assert results[0].clarification is not None


def test_nothing_resolved_reports_honest_gap():
    agent = FundamentalAnalystAgent(FakeFinnhubClient(profile={}))
    results = agent.execute(_context())

    assert "not sure which company" in results[0].facts[0]