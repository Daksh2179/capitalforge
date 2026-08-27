"""Unit tests for trading_cycle_service, against a real test Postgres
database, per our established pattern."""

import uuid
from datetime import datetime, timezone

from app.services import strategy_service, trading_cycle_service
from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.domain.order import Order, OrderSide, OrderStatus, OrderType
from app.trading_engine.domain.portfolio import Portfolio
from app.trading_engine.domain.position import Position
from app.trading_engine.domain.signal import Signal, SignalAction
from app.trading_engine.risk.risk_manager import RiskDecision


def _create_strategy_version(db_session):
    strategy = strategy_service.create_strategy(
        db_session,
        user_id=uuid.uuid4(),
        config_json={
            "schema_version": 1, "symbol": "AAPL",
            "conditions": {"operator": "AND", "rules": [
                {"indicator": "RSI", "period": 14, "operator": "less_than", "value": 30}
            ]},
            "capital_allocation": {"type": "percentage_of_portfolio", "percentage": 5},
            "exit": {"stop_loss_pct": 3, "take_profit_pct": None},
        },
        source="manual",
    )
    return strategy


def _bar() -> MarketBar:
    return MarketBar(
        symbol="AAPL", timestamp=datetime.now(timezone.utc),
        open=100, high=101, low=99, close=100.5, volume=1000.0,
    )


def test_log_decision_persists_with_no_risk_decision(db_session):
    strategy = _create_strategy_version(db_session)
    signal = Signal(
        symbol="AAPL", action=SignalAction.HOLD,
        timestamp=datetime.now(timezone.utc), evaluated=True,
    )

    log = trading_cycle_service.log_decision(
        db_session, strategy_version_id=strategy.current_version_id,
        latest_bar=_bar(), signal=signal, risk_decision=None,
    )

    assert log.action_taken == "hold"
    assert log.risk_approved is False
    assert "not evaluated by risk manager" in log.risk_reason


def test_log_decision_persists_with_risk_decision(db_session):
    strategy = _create_strategy_version(db_session)
    signal = Signal(
        symbol="AAPL", action=SignalAction.BUY,
        timestamp=datetime.now(timezone.utc), evaluated=True,
        triggered_rules=["RSI(14) < 30 (actual=25.0)"],
    )
    risk_decision = RiskDecision(approved=True, reason="approved", quantity=5.0)

    log = trading_cycle_service.log_decision(
        db_session, strategy_version_id=strategy.current_version_id,
        latest_bar=_bar(), signal=signal, risk_decision=risk_decision,
    )

    assert log.risk_approved is True
    assert len(log.rules_triggered_json) == 1


def test_record_order_persists_correctly(db_session):
    strategy = _create_strategy_version(db_session)
    domain_order = Order(
        id=uuid.uuid4(), symbol="AAPL", side=OrderSide.BUY,
        order_type=OrderType.MARKET, quantity=5.0, status=OrderStatus.NEW,
        submitted_at=datetime.now(timezone.utc),
    )

    order = trading_cycle_service.record_order(
        db_session, strategy_version_id=strategy.current_version_id, domain_order=domain_order
    )

    assert order.alpaca_order_id == str(domain_order.id)
    assert order.status == OrderStatus.NEW


def test_record_portfolio_snapshot_persists_correctly(db_session):
    strategy = _create_strategy_version(db_session)
    portfolio = Portfolio(
        cash=5000.0,
        positions={"AAPL": Position(symbol="AAPL", quantity=5, average_entry_price=100.0, current_price=105.0)},
    )

    snapshot = trading_cycle_service.record_portfolio_snapshot(
        db_session, strategy_id=strategy.id, portfolio=portfolio
    )

    assert snapshot.cash_balance == 5000.0
    assert snapshot.total_value == 5525.0
    assert snapshot.positions_json["AAPL"]["quantity"] == 5
    
def test_log_decision_persists_plan_outcome(db_session):
    strategy = _create_strategy_version(db_session)
    signal = Signal(
        symbol="AAPL", action=SignalAction.BUY,
        timestamp=datetime.now(timezone.utc), evaluated=True,
        triggered_rules=["RSI(14) < 30 (actual=25.0)"],
    )

    log = trading_cycle_service.log_decision(
        db_session, strategy_version_id=strategy.current_version_id,
        latest_bar=_bar(), signal=signal, risk_decision=None,
        plan_outcome="deferred",
    )

    assert log.plan_outcome == "deferred"


def test_log_decision_plan_outcome_defaults_to_none(db_session):
    strategy = _create_strategy_version(db_session)
    signal = Signal(
        symbol="AAPL", action=SignalAction.HOLD,
        timestamp=datetime.now(timezone.utc), evaluated=True,
    )

    log = trading_cycle_service.log_decision(
        db_session, strategy_version_id=strategy.current_version_id,
        latest_bar=_bar(), signal=signal, risk_decision=None,
    )

    assert log.plan_outcome is None
    
def test_list_non_terminal_orders_excludes_terminal_statuses(db_session):
    strategy = _create_strategy_version(db_session)
    non_terminal = Order(
        id=uuid.uuid4(), symbol="AAPL", side=OrderSide.BUY,
        order_type=OrderType.MARKET, quantity=5.0, status=OrderStatus.NEW,
        submitted_at=datetime.now(timezone.utc),
    )
    terminal = Order(
        id=uuid.uuid4(), symbol="AAPL", side=OrderSide.BUY,
        order_type=OrderType.MARKET, quantity=5.0, status=OrderStatus.FILLED,
        submitted_at=datetime.now(timezone.utc),
        filled_quantity=5.0, filled_avg_price=150.0, filled_at=datetime.now(timezone.utc),
    )
    trading_cycle_service.record_order(db_session, strategy_version_id=strategy.current_version_id, domain_order=non_terminal)
    trading_cycle_service.record_order(db_session, strategy_version_id=strategy.current_version_id, domain_order=terminal)

    results = trading_cycle_service.list_non_terminal_orders(db_session, strategy_id=strategy.id)

    assert len(results) == 1
    assert results[0].alpaca_order_id == str(non_terminal.id)


def test_list_non_terminal_orders_spans_all_versions_of_strategy(db_session):
    """The historical-GOOGL shape: a non-terminal order recorded under
    an OLDER version of the strategy must still be found when queried
    by strategy_id, not just the current version."""
    strategy = _create_strategy_version(db_session)
    old_version_id = strategy.current_version_id

    new_version = strategy_service.create_new_version(
        db_session, strategy=strategy,
        config_json={"schema_version": 1, "symbol": "AAPL", "conditions": {"operator": "AND", "rules": []},
                     "capital_allocation": {"type": "percentage_of_portfolio", "percentage": 5},
                     "exit": {"stop_loss_pct": 3, "take_profit_pct": None}},
        source="manual",
    )

    stale_order = Order(
        id=uuid.uuid4(), symbol="GOOGL", side=OrderSide.BUY,
        order_type=OrderType.MARKET, quantity=14.4, status=OrderStatus.NEW,
        submitted_at=datetime.now(timezone.utc),
    )
    trading_cycle_service.record_order(db_session, strategy_version_id=old_version_id, domain_order=stale_order)

    results = trading_cycle_service.list_non_terminal_orders(db_session, strategy_id=strategy.id)

    assert len(results) == 1
    assert results[0].alpaca_order_id == str(stale_order.id)
    assert results[0].strategy_version_id == old_version_id
    assert new_version.id != old_version_id  # sanity check the two versions really differ


def test_update_order_from_broker_overwrites_fields_from_alpaca(db_session):
    strategy = _create_strategy_version(db_session)
    domain_order = Order(
        id=uuid.uuid4(), symbol="AAPL", side=OrderSide.BUY,
        order_type=OrderType.MARKET, quantity=5.0, status=OrderStatus.NEW,
        submitted_at=datetime.now(timezone.utc),
    )
    order = trading_cycle_service.record_order(
        db_session, strategy_version_id=strategy.current_version_id, domain_order=domain_order
    )

    fill_time = datetime.now(timezone.utc)
    fresh = Order(
        id=domain_order.id, symbol="AAPL", side=OrderSide.BUY,
        order_type=OrderType.MARKET, quantity=5.0, status=OrderStatus.FILLED,
        submitted_at=domain_order.submitted_at,
        filled_quantity=5.0, filled_avg_price=152.34, filled_at=fill_time,
    )

    updated = trading_cycle_service.update_order_from_broker(db_session, order=order, fresh=fresh)

    assert updated.status == OrderStatus.FILLED
    assert updated.filled_quantity == 5.0
    assert updated.filled_avg_price == 152.34
    assert updated.filled_at == fill_time


def test_update_order_from_broker_handles_partial_fill_as_cumulative_overwrite(db_session):
    strategy = _create_strategy_version(db_session)
    domain_order = Order(
        id=uuid.uuid4(), symbol="AAPL", side=OrderSide.BUY,
        order_type=OrderType.MARKET, quantity=10.0, status=OrderStatus.NEW,
        submitted_at=datetime.now(timezone.utc),
    )
    order = trading_cycle_service.record_order(
        db_session, strategy_version_id=strategy.current_version_id, domain_order=domain_order
    )

    # First partial fill
    first_check = Order(
        id=domain_order.id, symbol="AAPL", side=OrderSide.BUY,
        order_type=OrderType.MARKET, quantity=10.0, status=OrderStatus.PARTIALLY_FILLED,
        submitted_at=domain_order.submitted_at, filled_quantity=4.0, filled_avg_price=150.0,
    )
    trading_cycle_service.update_order_from_broker(db_session, order=order, fresh=first_check)
    assert order.filled_quantity == 4.0

    # Second check: Alpaca reports the CUMULATIVE total, not a delta --
    # a correct sync overwrites, it never adds 6.0 + 4.0.
    second_check = Order(
        id=domain_order.id, symbol="AAPL", side=OrderSide.BUY,
        order_type=OrderType.MARKET, quantity=10.0, status=OrderStatus.FILLED,
        submitted_at=domain_order.submitted_at, filled_quantity=10.0, filled_avg_price=150.8,
        filled_at=datetime.now(timezone.utc),
    )
    trading_cycle_service.update_order_from_broker(db_session, order=order, fresh=second_check)

    assert order.filled_quantity == 10.0
    assert order.status == OrderStatus.FILLED