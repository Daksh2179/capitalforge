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