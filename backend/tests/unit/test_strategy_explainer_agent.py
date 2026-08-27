"""Unit tests for StrategyExplainerAgent."""

import uuid
from datetime import datetime, timezone

from app.agent.agents.strategy_explainer_agent import StrategyExplainerAgent
from app.agent.conversation_memory import ConversationEvent, ConversationMemory, EntityReference
from app.agent.pipeline.types import AgentExecutionContext, DetailLevel, GoalExtractionIntent, GroundedContext
from app.services import strategy_service


def _resolved(symbol: str):
    from app.agent.pipeline.types import ResolvedEntity
    return ResolvedEntity(
        raw_text=symbol,
        entity=EntityReference(kind="symbol", value=symbol, display_name=f"{symbol} Inc. ({symbol})"),
        explanation="test fixture",
    )


def _context(resolved_entities, memory, raw_message="why did you set that?") -> AgentExecutionContext:
    grounded = GroundedContext(
        intent=GoalExtractionIntent.EXPLAIN, goal_relation=None, goal_summary=None,
        resolved_entities=resolved_entities, raw_message=raw_message,
    )
    return AgentExecutionContext(grounded_context=grounded, memory=memory)


def test_explains_a_defaulted_value_honestly(db_session):
    memory = ConversationMemory(recent_events=[
        ConversationEvent(
            agent="strategy_builder", description="Added buy condition for AAPL",
            reasoning="AAPL was a new rule this turn, so its capital allocation defaulted to 5.0%.",
            related_entities=[EntityReference(kind="symbol", value="AAPL", display_name="Apple (AAPL)")],
            timestamp=datetime.now(timezone.utc),
        )
    ])
    agent = StrategyExplainerAgent(db_session)
    results = agent.execute(_context([_resolved("AAPL")], memory))

    assert "defaulted to 5.0%" in results[0].facts[0]


def test_explains_a_user_specified_value_honestly(db_session):
    memory = ConversationMemory(recent_events=[
        ConversationEvent(
            agent="strategy_builder", description="Set AAPL buy condition RSI(14) < 30",
            reasoning=None,
            related_entities=[EntityReference(kind="symbol", value="AAPL", display_name="Apple (AAPL)")],
            timestamp=datetime.now(timezone.utc),
        )
    ])
    agent = StrategyExplainerAgent(db_session)
    results = agent.execute(_context([_resolved("AAPL")], memory))

    assert "you specified that value directly" in results[0].facts[0]


def test_no_matching_event_reports_honest_gap_not_a_guess(db_session):
    agent = StrategyExplainerAgent(db_session)
    results = agent.execute(_context([_resolved("AAPL")], ConversationMemory()))

    assert "don't have a record" in results[0].facts[0]


def test_nothing_resolved_reports_honest_gap(db_session):
    agent = StrategyExplainerAgent(db_session)
    results = agent.execute(_context([], ConversationMemory(), raw_message="why did you set that stop loss?"))

    assert "not sure which rule" in results[0].facts[0]


def test_whole_strategy_explanation_narrates_rules_in_plain_english(db_session):
    strategy = strategy_service.create_strategy(
        db_session, user_id=uuid.uuid4(),
        config_json={
            "schema_version": 3,
            "portfolio_rules": {"cash_reserve_pct": 10, "max_open_positions": 5},
            "asset_rules": [{
                "symbol": "AAPL",
                "buy_conditions": {"operator": "AND", "rules": [{"indicator": "RSI", "period": 14, "operator": "less_than", "value": 30}]},
                "sell_conditions": {"operator": "AND", "rules": [{"indicator": "PRICE", "period": 1, "operator": "greater_than", "value": 200}]},
                "capital_allocation": {"type": "percentage_of_portfolio", "percentage": 10},
                "exit": {"stop_loss_pct": 5},
            }],
        },
        source="manual", confirmed_now=True,
    )
    db_session.refresh(strategy)

    agent = StrategyExplainerAgent(db_session)
    grounded = GroundedContext(
        intent=GoalExtractionIntent.EXPLAIN, goal_relation=None, goal_summary=None,
        raw_message="what is my strategy doing?",
    )
    context = AgentExecutionContext(grounded_context=grounded, memory=ConversationMemory(), strategy_id=strategy.id)

    results = agent.execute(context)

    facts_text = " ".join(results[0].facts)
    assert "RSI(14) drops below 30" in facts_text
    assert "10% of the portfolio" in facts_text
    assert "stop loss at 5%" in facts_text
    assert "keeps at least 10% of the portfolio in cash" in facts_text


def test_whole_strategy_explanation_expanded_gives_more_detail(db_session):
    strategy = strategy_service.create_strategy(
        db_session, user_id=uuid.uuid4(),
        config_json={
            "schema_version": 3, "portfolio_rules": {},
            "asset_rules": [{
                "symbol": "AAPL",
                "buy_conditions": {"operator": "AND", "rules": [{"indicator": "RSI", "period": 14, "operator": "less_than", "value": 30}]},
                "sell_conditions": {"operator": "AND", "rules": [{"indicator": "PRICE", "period": 1, "operator": "greater_than", "value": 200}]},
                "capital_allocation": {"type": "percentage_of_portfolio", "percentage": 10},
                "exit": {},
            }],
        },
        source="manual", confirmed_now=True,
    )
    db_session.refresh(strategy)

    agent = StrategyExplainerAgent(db_session)
    grounded = GroundedContext(
        intent=GoalExtractionIntent.EXPLAIN, goal_relation=None, goal_summary=None,
        raw_message="explain my strategy technically", detail_level=DetailLevel.EXPANDED,
    )
    context = AgentExecutionContext(grounded_context=grounded, memory=ConversationMemory(), strategy_id=strategy.id)

    results = agent.execute(context)

    assert "Buy condition (AND)" in results[0].facts[0]
    assert "Sell condition (AND)" in results[0].facts[0]


def test_whole_strategy_with_no_strategy_reports_honest_gap(db_session):
    agent = StrategyExplainerAgent(db_session)
    grounded = GroundedContext(
        intent=GoalExtractionIntent.EXPLAIN, goal_relation=None, goal_summary=None,
        raw_message="what is my robot doing?",
    )
    context = AgentExecutionContext(grounded_context=grounded, memory=ConversationMemory(), strategy_id=None)

    results = agent.execute(context)

    assert "don't have an active strategy" in results[0].facts[0]
    
def _strategy_with_rules(db_session, symbols):
    # Complete, schema-valid AssetRule dicts -- _symbol_has_rule
    # validates the whole StrategyConfig via Pydantic, which requires
    # every AssetRule field to be present. Real, production-persisted
    # configs always have this (they went through validation before
    # being saved); a bare {"symbol": s} only ever happens in an
    # under-built test fixture, which is exactly what broke here.
    strategy = strategy_service.create_strategy(
        db_session, user_id=uuid.uuid4(),
        config_json={
            "schema_version": 3, "portfolio_rules": {},
            "asset_rules": [
                {
                    "symbol": s,
                    "buy_conditions": {"operator": "AND", "rules": []},
                    "sell_conditions": {"operator": "AND", "rules": []},
                    "capital_allocation": {"type": "percentage_of_portfolio", "percentage": 5},
                    "exit": {},
                }
                for s in symbols
            ],
        },
        source="manual", confirmed_now=True,
    )
    db_session.refresh(strategy)
    return strategy


def test_widened_markers_route_rule_listing_question_to_whole_strategy(db_session):
    strategy = strategy_service.create_strategy(
        db_session, user_id=uuid.uuid4(),
        config_json={
            "schema_version": 3, "portfolio_rules": {},
            "asset_rules": [{
                "symbol": "AAPL",
                "buy_conditions": {"operator": "AND", "rules": [{"indicator": "RSI", "period": 14, "operator": "less_than", "value": 30}]},
                "sell_conditions": {"operator": "AND", "rules": []},
                "capital_allocation": {"type": "percentage_of_portfolio", "percentage": 5},
                "exit": {},
            }],
        },
        source="manual", confirmed_now=True,
    )
    db_session.refresh(strategy)

    agent = StrategyExplainerAgent(db_session)
    grounded = GroundedContext(
        intent=GoalExtractionIntent.REVIEW, goal_relation=None, goal_summary=None,
        raw_message="What symbols do I have trading rules for?",
    )
    context = AgentExecutionContext(grounded_context=grounded, memory=ConversationMemory(), strategy_id=strategy.id)

    results = agent.execute(context)

    assert "AAPL" in results[0].facts[0]
    assert results[0].description == "Explained the whole strategy"


def test_rule_existence_check_true_when_symbol_has_a_rule(db_session):
    strategy = _strategy_with_rules(db_session, ["AAPL"])
    agent = StrategyExplainerAgent(db_session)
    grounded = GroundedContext(
        intent=GoalExtractionIntent.EXPLAIN, goal_relation=None, goal_summary=None,
        resolved_entities=[_resolved("AAPL")], raw_message="Does AAPL have a rule?",
    )
    context = AgentExecutionContext(grounded_context=grounded, memory=ConversationMemory(), strategy_id=strategy.id)
    results = agent.execute(context)

    assert results[0].facts[0] == "AAPL currently has an AI-managed rule."


def test_rule_existence_check_false_when_symbol_has_no_rule(db_session):
    strategy = _strategy_with_rules(db_session, ["AAPL"])
    agent = StrategyExplainerAgent(db_session)
    grounded = GroundedContext(
        intent=GoalExtractionIntent.EXPLAIN, goal_relation=None, goal_summary=None,
        resolved_entities=[_resolved("NEE")], raw_message="Does NEE have a trading rule?",
    )
    context = AgentExecutionContext(grounded_context=grounded, memory=ConversationMemory(), strategy_id=strategy.id)
    results = agent.execute(context)

    assert results[0].facts[0] == "NEE doesn't currently have an AI-managed rule."


def test_rule_existence_check_ignores_memory_primary_focus(db_session):
    """An explicitly resolved NEE must be answered about directly, even
    with memory.primary_focus pointing at GOOGL from an earlier turn."""
    strategy = _strategy_with_rules(db_session, ["GOOGL"])
    memory = ConversationMemory(primary_focus=EntityReference(kind="symbol", value="GOOGL", display_name="Alphabet (GOOGL)"))

    agent = StrategyExplainerAgent(db_session)
    grounded = GroundedContext(
        intent=GoalExtractionIntent.EXPLAIN, goal_relation=None, goal_summary=None,
        resolved_entities=[_resolved("NEE")], raw_message="Does NEE have a rule?",
    )
    context = AgentExecutionContext(grounded_context=grounded, memory=memory, strategy_id=strategy.id)
    results = agent.execute(context)

    assert "NEE" in results[0].facts[0]
    assert "GOOGL" not in results[0].facts[0]


def test_per_edit_why_questions_are_unaffected_by_rule_existence_check(db_session):
    """Regression guard: a plain 'why did you set that' question with
    no rule-existence marker must still hit the original per-edit
    logic, not the new branch."""
    memory = ConversationMemory(recent_events=[
        ConversationEvent(
            agent="strategy_builder", description="Set AAPL buy condition RSI(14) < 30",
            reasoning=None,
            related_entities=[EntityReference(kind="symbol", value="AAPL", display_name="Apple (AAPL)")],
            timestamp=datetime.now(timezone.utc),
        )
    ])
    agent = StrategyExplainerAgent(db_session)
    results = agent.execute(_context([_resolved("AAPL")], memory))

    assert "you specified that value directly" in results[0].facts[0]