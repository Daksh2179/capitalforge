"""Unit tests for run_evaluation_cycle, using fake MarketDataProvider
and Broker implementations — no real Alpaca calls, no real money."""

import uuid
from datetime import datetime, timedelta, timezone

from app.services import strategy_service
from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.domain.order import Order, OrderSide, OrderStatus, OrderType
from app.trading_engine.domain.portfolio import Portfolio
from app.trading_engine.domain.position import Position
from app.trading_engine.execution.broker import Broker
from app.trading_engine.market_data.provider import MarketDataProvider
from app.workers.evaluation_job import run_evaluation_cycle


class FakeMarketDataProvider(MarketDataProvider):
    """closes_by_symbol lets a test control each symbol's bars
    independently -- needed now that a cycle can fetch bars for
    several symbols at once (every asset_rule's symbol, plus every
    currently held symbol)."""

    def __init__(self, closes_by_symbol: dict[str, list[float]]) -> None:
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self._bars_by_symbol = {
            symbol: [
                MarketBar(symbol=symbol, timestamp=base + timedelta(days=i),
                          open=c, high=c, low=c, close=c, volume=100_000.0)
                for i, c in enumerate(closes)
            ]
            for symbol, closes in closes_by_symbol.items()
        }

    def get_historical_bars(self, symbol, timeframe, start, end):
        return self._bars_by_symbol.get(symbol, [])


class FakeBroker(Broker):
    def __init__(self, cash: float = 10000.0, positions: dict | None = None) -> None:
        self.portfolio = Portfolio(cash=cash, positions=positions or {})
        self.placed_orders: list = []
        # Keyed by alpaca_order_id (as a string, matching how it's
        # stored/looked up everywhere else). A value of an Exception
        # instance means "raise this instead of returning" -- lets a
        # test simulate Alpaca being unreachable for one specific order.
        self.get_order_responses: dict[str, Order | Exception] = {}

    def get_portfolio(self) -> Portfolio:
        return self.portfolio

    def place_order(self, symbol, side, order_type, quantity, limit_price=None, stop_price=None) -> Order:
        order = Order(
            id=uuid.uuid4(), symbol=symbol, side=side, order_type=order_type,
            quantity=quantity, status=OrderStatus.NEW, submitted_at=datetime.now(timezone.utc),
        )
        self.placed_orders.append(order)
        if side == OrderSide.BUY:
            self.portfolio.cash -= quantity * (self._last_close(symbol) or 0.0)
        else:
            self.portfolio.cash += quantity * (self._last_close(symbol) or 0.0)
        return order

    def _last_close(self, symbol: str) -> float | None:
        position = self.portfolio.positions.get(symbol)
        return position.current_price if position else None

    def get_order(self, order_id: str) -> Order:
        response = self.get_order_responses.get(order_id)
        if response is None:
            raise NotImplementedError(f"FakeBroker.get_order: no response configured for {order_id!r}")
        if isinstance(response, Exception):
            raise response
        return response

    def cancel_order(self, order_id: str) -> None:
        raise NotImplementedError


def _create_strategy(db_session, symbol: str = "AAPL", max_open_positions: int | None = None):
    strategy = strategy_service.create_strategy(
        db_session,
        user_id=uuid.uuid4(),
        config_json={
            "schema_version": 3,
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
                "capital_allocation": {"type": "percentage_of_portfolio", "percentage": 5},
                "exit": {"stop_loss_pct": 3, "take_profit_pct": None},
            }],
        },
        source="manual",
    )
    db_session.refresh(strategy)
    return strategy


def test_evaluation_cycle_with_insufficient_data_logs_without_trading(db_session):
    strategy = _create_strategy(db_session)
    market_data = FakeMarketDataProvider({"AAPL": [1, 2, 3]})
    broker = FakeBroker()

    run_evaluation_cycle(
        db_session, strategy=strategy, strategy_version=strategy.current_version,
        market_data=market_data, broker=broker,
    )

    assert len(broker.placed_orders) == 0


def test_evaluation_cycle_executes_trade_when_conditions_hold(db_session):
    strategy = _create_strategy(db_session)
    closes = [float(i) for i in range(30, 0, -1)]  # descending -> RSI(14) < 30
    market_data = FakeMarketDataProvider({"AAPL": closes})
    broker = FakeBroker(cash=10000.0)

    run_evaluation_cycle(
        db_session, strategy=strategy, strategy_version=strategy.current_version,
        market_data=market_data, broker=broker,
    )

    assert len(broker.placed_orders) >= 1
    assert broker.placed_orders[0].side == OrderSide.BUY


def test_evaluation_cycle_sells_when_stop_loss_triggered(db_session):
    strategy = _create_strategy(db_session)
    market_data = FakeMarketDataProvider({"AAPL": [50.0] * 20})
    broker = FakeBroker(cash=1000.0, positions={
        "AAPL": Position(symbol="AAPL", quantity=5, average_entry_price=100.0, current_price=50.0)
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
    market_data = FakeMarketDataProvider({
        "AAPL": closes,
        "TSLA": [100.0] * 20,  # held position's bars, fetched for correlation
    })
    broker = FakeBroker(cash=10000.0, positions={
        "TSLA": Position(symbol="TSLA", quantity=1, average_entry_price=100.0, current_price=100.0)
    })

    run_evaluation_cycle(
        db_session, strategy=strategy, strategy_version=strategy.current_version,
        market_data=market_data, broker=broker,
    )

    assert len(broker.placed_orders) == 0


def test_evaluation_cycle_records_exactly_one_portfolio_snapshot(db_session):
    from app.services import trading_cycle_service

    strategy = _create_strategy(db_session)
    closes = [float(i) for i in range(30, 0, -1)]
    market_data = FakeMarketDataProvider({"AAPL": closes})
    broker = FakeBroker(cash=10000.0)

    run_evaluation_cycle(
        db_session, strategy=strategy, strategy_version=strategy.current_version,
        market_data=market_data, broker=broker,
    )

    snapshots = trading_cycle_service.list_portfolio_snapshots(db_session, strategy_id=strategy.id)
    assert len(snapshots) == 1
    
    
def test_evaluation_cycle_syncs_a_stale_pending_order(db_session):
    """The historical-GOOGL shape, reproduced directly: a non-terminal
    order sitting from a past cycle gets corrected to FILLED the next
    time this strategy is evaluated -- no separate reconciliation path,
    same sync_pending_orders() used for everything."""
    from app.services import trading_cycle_service

    strategy = _create_strategy(db_session)
    stale_order = Order(
        id=uuid.uuid4(), symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET,
        quantity=5.0, status=OrderStatus.NEW, submitted_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    trading_cycle_service.record_order(
        db_session, strategy_version_id=strategy.current_version_id, domain_order=stale_order
    )

    market_data = FakeMarketDataProvider({"AAPL": [50.0] * 20})  # flat: no new signal either way
    broker = FakeBroker(cash=10000.0)
    filled_version = Order(
        id=stale_order.id, symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET,
        quantity=5.0, status=OrderStatus.FILLED, submitted_at=stale_order.submitted_at,
        filled_quantity=5.0, filled_avg_price=151.20, filled_at=datetime.now(timezone.utc),
    )
    broker.get_order_responses[str(stale_order.id)] = filled_version

    run_evaluation_cycle(
        db_session, strategy=strategy, strategy_version=strategy.current_version,
        market_data=market_data, broker=broker,
    )

    orders = trading_cycle_service.list_orders(db_session, strategy_version_id=strategy.current_version_id, limit=10)
    synced = next(o for o in orders if o.alpaca_order_id == str(stale_order.id))
    assert synced.status == OrderStatus.FILLED
    assert synced.filled_quantity == 5.0
    assert synced.filled_avg_price == 151.20


def test_evaluation_cycle_leaves_order_untouched_when_alpaca_call_fails(db_session):
    from app.services import trading_cycle_service

    strategy = _create_strategy(db_session)
    stale_order = Order(
        id=uuid.uuid4(), symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET,
        quantity=5.0, status=OrderStatus.NEW, submitted_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    trading_cycle_service.record_order(
        db_session, strategy_version_id=strategy.current_version_id, domain_order=stale_order
    )

    market_data = FakeMarketDataProvider({"AAPL": [50.0] * 20})
    broker = FakeBroker(cash=10000.0)
    broker.get_order_responses[str(stale_order.id)] = ConnectionError("Alpaca unreachable")

    run_evaluation_cycle(
        db_session, strategy=strategy, strategy_version=strategy.current_version,
        market_data=market_data, broker=broker,
    )

    orders = trading_cycle_service.list_orders(db_session, strategy_version_id=strategy.current_version_id, limit=10)
    unchanged = next(o for o in orders if o.alpaca_order_id == str(stale_order.id))
    # Left exactly as it was -- not FILLED, not zeroed out, not guessed at.
    assert unchanged.status == OrderStatus.NEW
    assert unchanged.filled_quantity == 0.0


def test_evaluation_cycle_does_not_repoll_terminal_orders(db_session):
    """A FILLED order from a past cycle should never trigger a
    broker.get_order call again -- confirms list_non_terminal_orders'
    filter is actually wired into the cycle, not just unit-tested."""
    from app.services import trading_cycle_service

    strategy = _create_strategy(db_session)
    already_filled = Order(
        id=uuid.uuid4(), symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET,
        quantity=5.0, status=OrderStatus.FILLED, submitted_at=datetime.now(timezone.utc) - timedelta(days=1),
        filled_quantity=5.0, filled_avg_price=150.0, filled_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    trading_cycle_service.record_order(
        db_session, strategy_version_id=strategy.current_version_id, domain_order=already_filled
    )

    market_data = FakeMarketDataProvider({"AAPL": [50.0] * 20})
    broker = FakeBroker(cash=10000.0)
    # Deliberately NOT configuring a response for this order's id --
    # if the cycle tries to poll it anyway, FakeBroker.get_order raises
    # NotImplementedError and this test fails loudly.

    run_evaluation_cycle(
        db_session, strategy=strategy, strategy_version=strategy.current_version,
        market_data=market_data, broker=broker,
    )

    orders = trading_cycle_service.list_orders(db_session, strategy_version_id=strategy.current_version_id, limit=10)
    unchanged = next(o for o in orders if o.alpaca_order_id == str(already_filled.id))
    assert unchanged.status == OrderStatus.FILLED  # untouched, never re-fetched