"""Unit tests for run_evaluation_cycle, using fake MarketDataProvider
and Broker implementations — no real Alpaca calls, no real money."""

import uuid
from datetime import datetime, timedelta, timezone

from app.services import strategy_service
from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.domain.order import Order, OrderSide, OrderStatus
from app.trading_engine.domain.portfolio import Portfolio
from app.trading_engine.domain.position import Position
from app.trading_engine.execution.broker import Broker
from app.trading_engine.market_data.provider import MarketDataProvider
from app.workers.evaluation_job import run_evaluation_cycle


class FakeMarketDataProvider(MarketDataProvider):
    def __init__(self, closes: list[float], symbol: str = "AAPL") -> None:
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self._bars = [
            MarketBar(symbol=symbol, timestamp=base + timedelta(days=i),
                      open=c, high=c, low=c, close=c, volume=0.0)
            for i, c in enumerate(closes)
        ]

    def get_historical_bars(self, symbol, timeframe, start, end):
        return self._bars


class FakeBroker(Broker):
    def __init__(self, cash: float = 10000.0, positions: dict | None = None) -> None:
        self.portfolio = Portfolio(cash=cash, positions=positions or {})
        self.placed_orders: list = []

    def get_portfolio(self) -> Portfolio:
        return self.portfolio

    def place_order(self, symbol, side, order_type, quantity, limit_price=None, stop_price=None) -> Order:
        order = Order(
            id=uuid.uuid4(), symbol=symbol, side=side, order_type=order_type,
            quantity=quantity, status=OrderStatus.NEW, submitted_at=datetime.now(timezone.utc),
        )
        self.placed_orders.append(order)
        return order

    def get_order(self, order_id: str) -> Order:
        raise NotImplementedError

    def cancel_order(self, order_id: str) -> None:
        raise NotImplementedError


def _create_strategy(db_session, symbol: str = "AAPL", max_open_positions: int | None = None):
    strategy = strategy_service.create_strategy(
        db_session,
        user_id=uuid.uuid4(),
        config_json={
            "schema_version": 2,
            "portfolio_rules": {
                "cash_reserve_pct": None, "max_allocation_pct": None,
                "max_open_positions": max_open_positions,
            },
            "asset_rules": [{
                "symbol": symbol,
                "buy_conditions": {
                    "operator": "AND",
                    "rules": [{"indicator": "RSI", "period": 14, "operator": "less_than", "value": 30}],
                },
                "sell_conditions": {
                    "operator": "AND",
                    "rules": [{"indicator": "PRICE", "period": 1, "operator": "greater_than", "value": 999999999}],
                },
                "position_sizing": {"type": "fixed_allocation", "value_pct": 5},
                "exit": {"stop_loss_pct": 3, "take_profit_pct": None},
            }],
        },
        source="manual",
    )
    db_session.refresh(strategy)
    return strategy


def test_evaluation_cycle_with_insufficient_data_logs_without_trading(db_session):
    strategy = _create_strategy(db_session)
    market_data = FakeMarketDataProvider([1, 2, 3])
    broker = FakeBroker()

    run_evaluation_cycle(
        db_session, strategy=strategy, strategy_version=strategy.current_version,
        market_data=market_data, broker=broker,
    )

    assert len(broker.placed_orders) == 0


def test_evaluation_cycle_executes_trade_when_conditions_hold(db_session):
    strategy = _create_strategy(db_session)
    closes = [float(i) for i in range(30, 0, -1)]
    market_data = FakeMarketDataProvider(closes)
    broker = FakeBroker(cash=10000.0)

    run_evaluation_cycle(
        db_session, strategy=strategy, strategy_version=strategy.current_version,
        market_data=market_data, broker=broker,
    )

    assert len(broker.placed_orders) >= 1


def test_evaluation_cycle_sells_when_stop_loss_triggered(db_session):
    strategy = _create_strategy(db_session)
    market_data = FakeMarketDataProvider([50.0])
    broker = FakeBroker(cash=1000.0, positions={
        "AAPL": Position(symbol="AAPL", quantity=5, average_entry_price=100.0)
    })

    run_evaluation_cycle(
        db_session, strategy=strategy, strategy_version=strategy.current_version,
        market_data=market_data, broker=broker,
    )

    assert len(broker.placed_orders) == 1
    assert broker.placed_orders[0].side == OrderSide.SELL


def test_evaluation_cycle_respects_max_open_positions_from_portfolio_rules(db_session):
    strategy = _create_strategy(db_session, symbol="AAPL", max_open_positions=1)
    closes = [float(i) for i in range(30, 0, -1)]
    market_data = FakeMarketDataProvider(closes)
    broker = FakeBroker(cash=10000.0, positions={
        "TSLA": Position(symbol="TSLA", quantity=1, average_entry_price=100.0, current_price=100.0)
    })

    run_evaluation_cycle(
        db_session, strategy=strategy, strategy_version=strategy.current_version,
        market_data=market_data, broker=broker,
    )

    assert len(broker.placed_orders) == 0