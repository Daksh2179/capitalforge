"""Unit tests for StrategyExplainerAgent."""

from datetime import datetime, timezone

from app.agent.agents.strategy_explainer_agent import StrategyExplainerAgent
from app.agent.conversation_memory import ConversationEvent, ConversationMemory, EntityReference
from app.agent.pipeline.types import AgentExecutionContext, GoalExtractionIntent, GroundedContext


def _resolved(symbol: str):
    from app.agent.pipeline.types import ResolvedEntity
    return ResolvedEntity(
        raw_text=symbol,
        entity=EntityReference(kind="symbol", value=symbol, display_name=f"{symbol} Inc. ({symbol})"),
        explanation="test fixture",
    )


def _context(resolved_entities, memory) -> AgentExecutionContext:
    grounded = GroundedContext(
        intent=GoalExtractionIntent.EXPLAIN, goal_relation=None, goal_summary=None,
        resolved_entities=resolved_entities, raw_message="x",
    )
    return AgentExecutionContext(grounded_context=grounded, memory=memory)


def test_explains_a_defaulted_value_honestly():
    memory = ConversationMemory(recent_events=[
        ConversationEvent(
            agent="strategy_builder", description="Added buy condition for AAPL",
            reasoning="AAPL was a new rule this turn, so its capital allocation defaulted to 5.0%.",
            related_entities=[EntityReference(kind="symbol", value="AAPL", display_name="Apple (AAPL)")],
            timestamp=datetime.now(timezone.utc),
        )
    ])
    agent = StrategyExplainerAgent()
    results = agent.execute(_context([_resolved("AAPL")], memory))

    assert "defaulted to 5.0%" in results[0].facts[0]


def test_explains_a_user_specified_value_honestly():
    memory = ConversationMemory(recent_events=[
        ConversationEvent(
            agent="strategy_builder", description="Set AAPL buy condition RSI(14) < 30",
            reasoning=None,
            related_entities=[EntityReference(kind="symbol", value="AAPL", display_name="Apple (AAPL)")],
            timestamp=datetime.now(timezone.utc),
        )
    ])
    agent = StrategyExplainerAgent()
    results = agent.execute(_context([_resolved("AAPL")], memory))

    assert "you specified that value directly" in results[0].facts[0]


def test_no_matching_event_reports_honest_gap_not_a_guess():
    agent = StrategyExplainerAgent()
    results = agent.execute(_context([_resolved("AAPL")], ConversationMemory()))

    assert "don't have a record" in results[0].facts[0]


def test_nothing_resolved_reports_honest_gap():
    agent = StrategyExplainerAgent()
    results = agent.execute(_context([], ConversationMemory()))

    assert "not sure which rule" in results[0].facts[0]