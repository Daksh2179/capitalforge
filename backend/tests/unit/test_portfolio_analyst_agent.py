"""Unit tests for PortfolioAnalystAgent -- real db_session data
(Strategy/DecisionLog/Order/PortfolioSnapshot/PortfolioHolding rows)."""

import uuid
from datetime import datetime, timezone

from app.agent.agents.portfolio_analyst_agent import PortfolioAnalystAgent
from app.agent.conversation_memory import ConversationMemory, EntityReference
from app.agent.pipeline.types import AgentExecutionContext, GoalExtractionIntent, GroundedContext, ResolvedEntity
from app.models.decision_log import DecisionLog
from app.models.order import Order
from app.models.portfolio_holding import PortfolioHolding
from app.models.portfolio_snapshot import PortfolioSnapshot
from app.services import strategy_service
from app.trading_engine.domain.order import OrderSide, OrderStatus, OrderType


def _create_strategy(db_session, asset_rules=None):
    strategy = strategy_service.create_strategy(
        db_session, user_id=uuid.uuid4(),
        config_json={"schema_version": 3, "portfolio_rules": {}, "asset_rules": asset_rules or []},
        source="manual", confirmed_now=True,
    )
    db_session.refresh(strategy)
    return strategy


def _resolved(symbol: str) -> ResolvedEntity:
    return ResolvedEntity(
        raw_text=symbol, entity=EntityReference(kind="symbol", value=symbol, display_name=f"{symbol} Inc. ({symbol})"),
        explanation="test fixture",
    )


def _context(
    strategy_id=None, user_id=None, resolved_entities=None, raw_message="x", memory=None
) -> AgentExecutionContext:
    grounded = GroundedContext(
        intent=GoalExtractionIntent.REVIEW, goal_relation=None, goal_summary=None,
        resolved_entities=resolved_entities or [], raw_message=raw_message,
    )
    return AgentExecutionContext(
        grounded_context=grounded, memory=memory or ConversationMemory(),
        strategy_id=strategy_id, user_id=user_id,
    )


def _order(strategy_version_id, symbol, side, status, quantity=5.0, filled_quantity=0.0, filled_avg_price=None, filled_at=None):
    return Order(
        strategy_version_id=strategy_version_id,
        alpaca_order_id=str(uuid.uuid4()),
        symbol=symbol, side=side, order_type=OrderType.MARKET,
        quantity=quantity, status=status,
        filled_quantity=filled_quantity, filled_avg_price=filled_avg_price,
        submitted_at=datetime.now(timezone.utc), filled_at=filled_at,
    )


def test_no_strategy_no_watchlist_reports_honest_gap(db_session):
    agent = PortfolioAnalystAgent(db_session)
    results = agent.execute(_context())
    assert "don't have anything on your watchlist or an active strategy" in results[0].facts[0]


def test_watchlist_only_no_strategy_reports_useful_summary(db_session):
    user_id = uuid.uuid4()
    db_session.add(PortfolioHolding(user_id=user_id, symbol="AAPL"))
    db_session.commit()

    agent = PortfolioAnalystAgent(db_session)
    results = agent.execute(_context(user_id=user_id))

    assert "AAPL" in results[0].facts[0]
    assert "without an AI-managed rule" in results[0].facts[0]


def test_watchlist_symbol_with_ai_rule_is_distinguished(db_session):
    user_id = uuid.uuid4()
    strategy = strategy_service.create_strategy(
        db_session, user_id=user_id,
        config_json={"schema_version": 3, "portfolio_rules": {}, "asset_rules": [{"symbol": "AAPL"}]},
        source="manual", confirmed_now=True,
    )
    strategy.state = "active"
    db_session.add(PortfolioHolding(user_id=user_id, symbol="AAPL"))
    db_session.commit()

    agent = PortfolioAnalystAgent(db_session)
    results = agent.execute(_context(user_id=user_id, resolved_entities=[_resolved("AAPL")]))

    assert "already has an AI-managed rule" in results[0].facts[0]


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
    results = agent.execute(_context(strategy_id=strategy.id, resolved_entities=[_resolved("AAPL")]))

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
    results = agent.execute(_context(strategy_id=strategy.id, resolved_entities=[_resolved("AAPL")]))

    assert "haven't triggered recently" in results[0].facts[0]


def test_no_history_no_watchlist_for_symbol_reports_honest_gap(db_session):
    strategy = _create_strategy(db_session)
    agent = PortfolioAnalystAgent(db_session)
    results = agent.execute(_context(strategy_id=strategy.id, resolved_entities=[_resolved("AAPL")]))

    assert "don't have any information on AAPL" in results[0].facts[0]


def test_strategy_summary_reports_latest_snapshot(db_session):
    strategy = _create_strategy(db_session)
    db_session.add(PortfolioSnapshot(
        strategy_id=strategy.id, timestamp=datetime.now(timezone.utc),
        cash_balance=8500.0, positions_json={"AAPL": {"quantity": 5}}, total_value=9500.0,
    ))
    db_session.commit()

    agent = PortfolioAnalystAgent(db_session)
    results = agent.execute(_context(strategy_id=strategy.id))

    facts_text = " ".join(results[0].facts)
    assert "8500.00" in facts_text
    assert "9500.00" in facts_text
    assert "AAPL" in facts_text


def test_no_snapshot_yet_reports_honest_gap(db_session):
    strategy = _create_strategy(db_session)
    agent = PortfolioAnalystAgent(db_session)
    results = agent.execute(_context(strategy_id=strategy.id))
    assert "don't have a recorded portfolio snapshot" in results[0].facts[0]


def test_held_position_is_true_when_symbol_in_latest_snapshot(db_session):
    strategy = _create_strategy(db_session)
    db_session.add(PortfolioSnapshot(
        strategy_id=strategy.id, timestamp=datetime.now(timezone.utc),
        cash_balance=1000.0, positions_json={"AAPL": {"quantity": 5, "current_price": 190.0}},
        total_value=1950.0,
    ))
    db_session.commit()

    agent = PortfolioAnalystAgent(db_session)
    results = agent.execute(_context(strategy_id=strategy.id, resolved_entities=[_resolved("AAPL")]))
    assert results[0].held_position is True


def test_held_position_is_false_when_symbol_not_in_latest_snapshot(db_session):
    strategy = _create_strategy(db_session)
    db_session.add(PortfolioSnapshot(
        strategy_id=strategy.id, timestamp=datetime.now(timezone.utc),
        cash_balance=1000.0, positions_json={}, total_value=1000.0,
    ))
    db_session.commit()

    agent = PortfolioAnalystAgent(db_session)
    results = agent.execute(_context(strategy_id=strategy.id, resolved_entities=[_resolved("AAPL")]))
    assert results[0].held_position is False


def test_summary_includes_health_counts_from_decision_logs(db_session):
    strategy = _create_strategy(db_session)
    db_session.add(PortfolioSnapshot(
        strategy_id=strategy.id, timestamp=datetime.now(timezone.utc),
        cash_balance=1000.0, positions_json={}, total_value=1000.0,
    ))
    db_session.add(DecisionLog(
        strategy_version_id=strategy.current_version_id, timestamp=datetime.now(timezone.utc),
        market_snapshot_json={"symbol": "AAPL", "close": 190.0}, rules_triggered_json=[],
        action_taken="buy", risk_approved=True, risk_reason="approved", plan_outcome="selected",
    ))
    db_session.add(DecisionLog(
        strategy_version_id=strategy.current_version_id, timestamp=datetime.now(timezone.utc),
        market_snapshot_json={"symbol": "NVDA", "close": 200.0}, rules_triggered_json=[],
        action_taken="buy", risk_approved=False, risk_reason="deferred: capital already committed",
        plan_outcome="deferred",
    ))
    db_session.add(DecisionLog(
        strategy_version_id=strategy.current_version_id, timestamp=datetime.now(timezone.utc),
        market_snapshot_json={"symbol": "AAPL", "close": 190.0}, rules_triggered_json=[],
        action_taken="hold", risk_approved=False, risk_reason="not evaluated by risk manager",
    ))
    db_session.commit()

    agent = PortfolioAnalystAgent(db_session)
    results = agent.execute(_context(strategy.id))

    facts_text = " ".join(results[0].facts)
    assert "1 resulted in no action" in facts_text
    assert "2 buy condition(s) triggered (1 executed, 1 deferred" in facts_text
    assert "most recent buy/sell trigger was 0 day(s) ago" in facts_text


def test_summary_reports_no_trigger_history_honestly(db_session):
    strategy = _create_strategy(db_session)
    db_session.add(PortfolioSnapshot(
        strategy_id=strategy.id, timestamp=datetime.now(timezone.utc),
        cash_balance=1000.0, positions_json={}, total_value=1000.0,
    ))
    db_session.add(DecisionLog(
        strategy_version_id=strategy.current_version_id, timestamp=datetime.now(timezone.utc),
        market_snapshot_json={"symbol": "AAPL", "close": 190.0}, rules_triggered_json=[],
        action_taken="hold", risk_approved=False, risk_reason="not evaluated by risk manager",
    ))
    db_session.commit()

    agent = PortfolioAnalystAgent(db_session)
    results = agent.execute(_context(strategy.id))

    facts_text = " ".join(results[0].facts)
    assert "No buy or sell condition has triggered in the recorded history" in facts_text


# --- New tests below: order history, the NEM-shaped visibility fix,
# the explicit held-position statement, and the primary_focus guard. ---


def test_nem_shaped_symbol_has_rule_but_no_watchlist_entry_is_visible(db_session):
    """A symbol with a real AssetRule but NO PortfolioHolding row --
    the exact NEM shape. Previously invisible: is_symbol_ai_configured
    was only checked when the symbol was ALSO on the watchlist.

    is_symbol_ai_configured also requires Strategy.state != "draft"
    (confirmed_now=True alone only sets the version's confirmed_at, it
    doesn't change Strategy.state) -- matching the pattern the
    pre-existing test_watchlist_symbol_with_ai_rule_is_distinguished
    already uses.
    """
    strategy = _create_strategy(db_session, asset_rules=[{"symbol": "NEM"}])
    strategy.state = "active"
    db_session.commit()
    # Deliberately no PortfolioHolding row for NEM at all.

    agent = PortfolioAnalystAgent(db_session)
    results = agent.execute(_context(
        strategy_id=strategy.id, user_id=strategy.user_id, resolved_entities=[_resolved("NEM")],
    ))

    assert "isn't on your portfolio watchlist, but it does have an AI-managed rule" in results[0].facts[0]


def test_held_position_true_is_stated_explicitly_even_with_no_rule_or_watchlist_entry(db_session):
    """The GOOGL-under-an-old-strategy-version shape: a real position
    exists with neither a rule nor a watchlist entry. held_position
    must still be surfaced as a plain textual fact, not just the
    structured field."""
    strategy = _create_strategy(db_session)  # no asset_rules at all
    db_session.add(PortfolioSnapshot(
        strategy_id=strategy.id, timestamp=datetime.now(timezone.utc),
        cash_balance=1000.0, positions_json={"GOOGL": {"quantity": 10, "current_price": 190.0}},
        total_value=2900.0,
    ))
    db_session.commit()

    agent = PortfolioAnalystAgent(db_session)
    results = agent.execute(_context(strategy_id=strategy.id, resolved_entities=[_resolved("GOOGL")]))

    facts_text = " ".join(results[0].facts)
    assert "You currently hold a position in GOOGL" in facts_text
    assert results[0].held_position is True


def test_order_history_lists_real_orders(db_session):
    strategy = _create_strategy(db_session)
    fill_time = datetime.now(timezone.utc)
    db_session.add(_order(
        strategy.current_version_id, "AAPL", OrderSide.BUY, OrderStatus.FILLED,
        quantity=5.0, filled_quantity=5.0, filled_avg_price=190.5, filled_at=fill_time,
    ))
    db_session.commit()

    agent = PortfolioAnalystAgent(db_session)
    results = agent.execute(_context(strategy_id=strategy.id, raw_message="Show me my order history"))

    facts_text = " ".join(results[0].facts)
    assert "Buy AAPL" in facts_text
    assert "190.50" in facts_text


def test_order_history_reports_non_terminal_status_honestly(db_session):
    strategy = _create_strategy(db_session)
    db_session.add(_order(strategy.current_version_id, "AAPL", OrderSide.BUY, OrderStatus.NEW, quantity=5.0))
    db_session.commit()

    agent = PortfolioAnalystAgent(db_session)
    results = agent.execute(_context(strategy_id=strategy.id, raw_message="What did my strategy buy?"))

    facts_text = " ".join(results[0].facts)
    assert "status: new" in facts_text


def test_order_history_filters_by_resolved_symbol(db_session):
    strategy = _create_strategy(db_session)
    db_session.add(_order(strategy.current_version_id, "AAPL", OrderSide.BUY, OrderStatus.FILLED,
                           filled_quantity=5.0, filled_avg_price=190.0, filled_at=datetime.now(timezone.utc)))
    db_session.add(_order(strategy.current_version_id, "NVDA", OrderSide.BUY, OrderStatus.FILLED,
                           filled_quantity=2.0, filled_avg_price=800.0, filled_at=datetime.now(timezone.utc)))
    db_session.commit()

    agent = PortfolioAnalystAgent(db_session)
    results = agent.execute(_context(
        strategy_id=strategy.id, resolved_entities=[_resolved("AAPL")],
        raw_message="What did my strategy buy for AAPL?",
    ))

    facts_text = " ".join(results[0].facts)
    assert "AAPL" in facts_text
    assert "NVDA" not in facts_text


def test_order_history_empty_reports_honest_gap(db_session):
    strategy = _create_strategy(db_session)
    agent = PortfolioAnalystAgent(db_session)
    results = agent.execute(_context(strategy_id=strategy.id, raw_message="Show me my order history"))
    assert "don't have any recorded orders" in results[0].facts[0]


def test_order_history_no_active_strategy_reports_honest_gap(db_session):
    agent = PortfolioAnalystAgent(db_session)
    results = agent.execute(_context(raw_message="Show me my order history"))
    assert "don't have an active strategy" in results[0].facts[0]


def test_explicit_resolved_symbol_overrides_memory_primary_focus(db_session):
    """An explicitly resolved entity (NEE) must be answered about
    directly, never silently substituted with whatever
    memory.primary_focus happens to be set to (GOOGL) from an earlier,
    unrelated turn."""
    strategy = _create_strategy(db_session, asset_rules=[{"symbol": "NEE"}])
    memory = ConversationMemory(primary_focus=EntityReference(kind="symbol", value="GOOGL", display_name="Alphabet (GOOGL)"))

    agent = PortfolioAnalystAgent(db_session)
    results = agent.execute(_context(
        strategy_id=strategy.id, resolved_entities=[_resolved("NEE")], memory=memory,
    ))

    facts_text = " ".join(results[0].facts)
    assert "NEE" in facts_text
    assert "GOOGL" not in facts_text