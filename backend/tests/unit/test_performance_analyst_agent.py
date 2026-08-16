"""Unit tests for PerformanceAnalystAgent -- real db_session data,
same convention as PortfolioAnalystAgent/RiskAdvisorAgent."""

import uuid
from datetime import datetime, timedelta, timezone

from app.agent.agents.performance_analyst_agent import PerformanceAnalystAgent
from app.agent.conversation_memory import ConversationMemory, EntityReference
from app.agent.pipeline.types import AgentExecutionContext, GoalExtractionIntent, GroundedContext, ResolvedEntity
from app.models.portfolio_snapshot import PortfolioSnapshot
from app.services import strategy_service


def _create_strategy(db_session):
    strategy = strategy_service.create_strategy(
        db_session, user_id=uuid.uuid4(),
        config_json={"schema_version": 3, "portfolio_rules": {}, "asset_rules": []}, source="manual",
    )
    db_session.refresh(strategy)
    return strategy


def _add_snapshot(db_session, strategy_id, total_value, positions_json=None, days_ago=0):
    db_session.add(PortfolioSnapshot(
        strategy_id=strategy_id, timestamp=datetime.now(timezone.utc) - timedelta(days=days_ago),
        cash_balance=total_value, positions_json=positions_json or {}, total_value=total_value,
    ))
    db_session.commit()


def _resolved(symbol: str) -> ResolvedEntity:
    return ResolvedEntity(
        raw_text=symbol, entity=EntityReference(kind="symbol", value=symbol, display_name=symbol),
        explanation="test fixture",
    )


def _context(strategy_id, resolved_entities=None) -> AgentExecutionContext:
    grounded = GroundedContext(
        intent=GoalExtractionIntent.REVIEW, goal_relation=None, goal_summary=None,
        resolved_entities=resolved_entities or [], raw_message="x",
    )
    return AgentExecutionContext(grounded_context=grounded, memory=ConversationMemory(), strategy_id=strategy_id)


def test_no_strategy_id_reports_honest_gap(db_session):
    agent = PerformanceAnalystAgent(db_session)
    results = agent.execute(_context(strategy_id=None))
    assert "don't have an active strategy" in results[0].facts[0]


def test_single_snapshot_reports_not_enough_history(db_session):
    strategy = _create_strategy(db_session)
    _add_snapshot(db_session, strategy.id, total_value=10000.0)

    agent = PerformanceAnalystAgent(db_session)
    results = agent.execute(_context(strategy.id))

    assert "enough recorded history" in results[0].facts[0]


def test_total_return_computed_correctly_across_snapshots(db_session):
    strategy = _create_strategy(db_session)
    _add_snapshot(db_session, strategy.id, total_value=10000.0, days_ago=2)
    _add_snapshot(db_session, strategy.id, total_value=11000.0, days_ago=0)

    agent = PerformanceAnalystAgent(db_session)
    results = agent.execute(_context(strategy.id))

    assert "+10.00%" in results[0].facts[0]
    assert "win rate" in results[0].facts[-1]  # honest gap always stated


def test_max_drawdown_computed_correctly(db_session):
    strategy = _create_strategy(db_session)
    _add_snapshot(db_session, strategy.id, total_value=10000.0, days_ago=3)
    _add_snapshot(db_session, strategy.id, total_value=12000.0, days_ago=2)  # peak
    _add_snapshot(db_session, strategy.id, total_value=9000.0, days_ago=1)  # trough: 25% down from peak
    _add_snapshot(db_session, strategy.id, total_value=10500.0, days_ago=0)

    agent = PerformanceAnalystAgent(db_session)
    results = agent.execute(_context(strategy.id))

    assert "25.00%" in results[0].facts[1]


def test_symbol_currently_held_reports_unrealized_return(db_session):
    strategy = _create_strategy(db_session)
    _add_snapshot(db_session, strategy.id, total_value=10000.0, days_ago=1)
    _add_snapshot(
        db_session, strategy.id, total_value=10500.0, days_ago=0,
        positions_json={"AAPL": {"quantity": 5, "average_entry_price": 180.0, "current_price": 198.0}},
    )

    agent = PerformanceAnalystAgent(db_session)
    results = agent.execute(_context(strategy.id, resolved_entities=[_resolved("AAPL")]))

    assert "+10.00%" in results[0].facts[0]


def test_symbol_not_currently_held_reports_honest_gap(db_session):
    strategy = _create_strategy(db_session)
    _add_snapshot(db_session, strategy.id, total_value=10000.0)

    agent = PerformanceAnalystAgent(db_session)
    results = agent.execute(_context(strategy.id, resolved_entities=[_resolved("AAPL")]))

    assert "isn't currently held" in results[0].facts[0]