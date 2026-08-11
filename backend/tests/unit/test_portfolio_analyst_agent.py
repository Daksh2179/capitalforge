"""Unit tests for PortfolioAnalystAgent -- uses real db_session data
(Strategy/DecisionLog/Order/PortfolioSnapshot rows), not fakes, since
this Agent's whole job is reading real persisted history."""

import uuid
from datetime import datetime, timezone

from app.agent.agents.portfolio_analyst_agent import PortfolioAnalystAgent
from app.agent.conversation_memory import ConversationMemory, EntityReference
from app.agent.pipeline.types import AgentExecutionContext, GoalExtractionIntent, GroundedContext, ResolvedEntity
from app.models.decision_log import DecisionLog
from app.models.portfolio_snapshot import PortfolioSnapshot
from app.services import strategy_service


def _create_strategy(db_session):
    strategy = strategy_service.create_strategy(
        db_session, user_id=uuid.uuid4(),
        config_json={"schema_version": 3, "portfolio_rules": {}, "asset_rules": []},
        source="manual",
    )
    db_session.refresh(strategy)
    return strategy


def _resolved(symbol: str) -> ResolvedEntity:
    return ResolvedEntity(
        raw_text=symbol,
        entity=EntityReference(kind="symbol", value=symbol, display_name=f"{symbol} Inc. ({symbol})"),
        explanation="test fixture",
    )


def _context(strategy_id, resolved_entities=None) -> AgentExecutionContext:
    grounded = GroundedContext(
        intent=GoalExtractionIntent.REVIEW, goal_relation=None, goal_summary=None,
        resolved_entities=resolved_entities or [], raw_message="x",
    )
    return AgentExecutionContext(grounded_context=grounded, memory=ConversationMemory(), strategy_id=strategy_id)


def test_no_strategy_id_reports_honest_gap(db_session):
    agent = PortfolioAnalystAgent(db_session)
    results = agent.execute(_context(strategy_id=None))
    assert "don't have an active strategy" in results[0].facts[0]


def test_deferred_buy_reports_the_real_persisted_reason(db_session):
    strategy = _create_strategy(db_session)
    db_session.add(DecisionLog(
        strategy_version_id=strategy.current_version_id, timestamp=datetime.now(timezone.utc),
        market_snapshot_json={"symbol": "AAPL", "close": 190.0}, rules_triggered_json=[],
        action_taken="buy", risk_approved=False, risk_reason="deferred: capital already committed to NVDA",
        plan_outcome="deferred",
    ))
    db_session.commit()

    agent = PortfolioAnalystAgent(db_session)
    results = agent.execute(_context(strategy.id, resolved_entities=[_resolved("AAPL")]))

    assert "deferred: capital already committed to NVDA" in results[0].facts[0]


def test_condition_never_triggered_reports_honest_limitation_not_a_guess(db_session):
    strategy = _create_strategy(db_session)
    db_session.add(DecisionLog(
        strategy_version_id=strategy.current_version_id, timestamp=datetime.now(timezone.utc),
        market_snapshot_json={"symbol": "AAPL", "close": 190.0}, rules_triggered_json=[],
        action_taken="hold", risk_approved=False, risk_reason="not evaluated by risk manager",
    ))
    db_session.commit()

    agent = PortfolioAnalystAgent(db_session)
    results = agent.execute(_context(strategy.id, resolved_entities=[_resolved("AAPL")]))

    assert "haven't triggered recently" in results[0].facts[0]


def test_no_history_for_symbol_reports_honest_gap(db_session):
    strategy = _create_strategy(db_session)
    agent = PortfolioAnalystAgent(db_session)
    results = agent.execute(_context(strategy.id, resolved_entities=[_resolved("AAPL")]))

    assert "don't have any recent evaluation history" in results[0].facts[0]


def test_strategy_summary_reports_latest_snapshot(db_session):
    strategy = _create_strategy(db_session)
    db_session.add(PortfolioSnapshot(
        strategy_id=strategy.id, timestamp=datetime.now(timezone.utc),
        cash_balance=8500.0, positions_json={"AAPL": {"quantity": 5}}, total_value=9500.0,
    ))
    db_session.commit()

    agent = PortfolioAnalystAgent(db_session)
    results = agent.execute(_context(strategy.id))

    assert "8500.00" in results[0].facts[0]
    assert "9500.00" in results[0].facts[0]
    assert "AAPL" in results[0].facts[0]


def test_no_snapshot_yet_reports_honest_gap(db_session):
    strategy = _create_strategy(db_session)
    agent = PortfolioAnalystAgent(db_session)
    results = agent.execute(_context(strategy.id))

    assert "don't have a recorded portfolio snapshot" in results[0].facts[0]