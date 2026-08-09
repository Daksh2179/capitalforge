"""End-to-end scenario tests for run_evaluation_cycle: multiple
mechanisms interacting within one real cycle, verified against actual
persisted DecisionLog/Order/PortfolioSnapshot rows -- not just
in-memory assertions on a fake broker. Existing unit tests cover each
mechanism (planner, risk manager, evaluation_job) in isolation; this
file closes the gap between them.
"""

import uuid
from datetime import datetime, timedelta, timezone

from app.services import strategy_service, trading_cycle_service
from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.domain.order import Order, OrderSide, OrderStatus
from app.trading_engine.domain.portfolio import Portfolio
from app.trading_engine.domain.position import Position
from app.trading_engine.execution.broker import Broker
from app.trading_engine.market_data.provider import MarketDataProvider
from app.models.strategy import StrategyVersionSource
from app.workers.evaluation_job import run_evaluation_cycle

ALWAYS_TRIGGERS_BUY = 999_999_999  # PRICE less_than this is always true
NEVER_TRIGGERS_SELL = 999_999_999  # PRICE greater_than this is never true


class FakeMarketDataProvider(MarketDataProvider):
    def __init__(self, bars_by_symbol: dict[str, list[MarketBar]]) -> None:
        self._bars_by_symbol = bars_by_symbol

    def get_historical_bars(self, symbol, timeframe, start, end):
        return self._bars_by_symbol.get(symbol, [])


class FakeBroker(Broker):
    """Faithful enough to chain a SELL and a BUY within one cycle:
    place_order actually mutates self.portfolio.positions (removes a
    fully-closed SELL, adds/increases a BUY), not just cash. prices is
    the authoritative fill price per symbol -- kept separate from
    whatever bars a test constructs, so cash math is exact and doesn't
    depend on reading back a position that may not exist yet.
    """

    def __init__(
        self, cash: float, positions: dict[str, Position] | None = None,
        prices: dict[str, float] | None = None,
    ) -> None:
        self.portfolio = Portfolio(cash=cash, positions=dict(positions or {}))
        self.prices = prices or {}
        self.placed_orders: list[Order] = []

    def get_portfolio(self) -> Portfolio:
        return self.portfolio

    def place_order(self, symbol, side, order_type, quantity, limit_price=None, stop_price=None) -> Order:
        price = self.prices[symbol]
        order = Order(
            id=uuid.uuid4(), symbol=symbol, side=side, order_type=order_type,
            quantity=quantity, status=OrderStatus.NEW, submitted_at=datetime.now(timezone.utc),
        )
        self.placed_orders.append(order)

        if side == OrderSide.BUY:
            self.portfolio.cash -= quantity * price
            existing = self.portfolio.positions.get(symbol)
            new_quantity = (existing.quantity if existing else 0.0) + quantity
            self.portfolio.positions[symbol] = Position(
                symbol=symbol, quantity=new_quantity, average_entry_price=price, current_price=price,
            )
        else:
            self.portfolio.cash += quantity * price
            existing = self.portfolio.positions.get(symbol)
            existing_quantity = existing.quantity if existing else 0.0
            remaining = existing_quantity - quantity
            if existing is None or remaining <= 0:
                self.portfolio.positions.pop(symbol, None)
            else:
                self.portfolio.positions[symbol] = Position(
                    symbol=symbol, quantity=remaining,
                    average_entry_price=existing.average_entry_price, current_price=price,
                )
        return order

    def get_order(self, order_id: str) -> Order:
        raise NotImplementedError

    def cancel_order(self, order_id: str) -> None:
        raise NotImplementedError


def _flat_bars(symbol: str, price: float, count: int = 25, volume: float = 100_000.0) -> list[MarketBar]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        MarketBar(symbol=symbol, timestamp=base + timedelta(days=i),
                  open=price, high=price, low=price, close=price, volume=volume)
        for i in range(count)
    ]


def _bars_from_closes(symbol: str, closes: list[float], volume: float = 100_000.0) -> list[MarketBar]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        MarketBar(symbol=symbol, timestamp=base + timedelta(days=i),
                  open=c, high=c, low=c, close=c, volume=volume)
        for i, c in enumerate(closes)
    ]


def _negated_returns_series(base_closes: list[float], start_price: float) -> list[float]:
    """A price series whose daily returns are the exact negation of
    base_closes' returns -- guarantees Pearson correlation of exactly
    -1 against a series built from base_closes, regardless of the
    absolute price levels involved."""
    prices = [start_price]
    for prev, curr in zip(base_closes, base_closes[1:]):
        base_return = (curr - prev) / prev
        prices.append(prices[-1] * (1 - base_return))
    return prices


def _asset_rule(
    symbol: str, *, buy_threshold: float, capital: dict,
    created_at: str | None = None,
) -> dict:
    rule = {
        "symbol": symbol,
        "buy_conditions": {"operator": "AND", "rules": [
            {"indicator": "PRICE", "period": 1, "operator": "less_than", "value": buy_threshold}
        ]},
        "sell_conditions": {"operator": "AND", "rules": [
            {"indicator": "PRICE", "period": 1, "operator": "greater_than", "value": NEVER_TRIGGERS_SELL}
        ]},
        "capital_allocation": capital,
        "exit": {"stop_loss_pct": 3, "take_profit_pct": None},
    }
    if created_at is not None:
        rule["created_at"] = created_at
        rule["updated_at"] = created_at
    return rule


def _create_strategy(db_session, asset_rules: list[dict], portfolio_rules: dict | None = None):
    strategy = strategy_service.create_strategy(
        db_session,
        user_id=uuid.uuid4(),
        config_json={
            "schema_version": 3,
            "portfolio_rules": portfolio_rules or {
                "cash_reserve_pct": None, "max_allocation_pct": None,
                "max_open_positions": None, "total_capital_usd": None,
            },
            "asset_rules": asset_rules,
        },
        source=StrategyVersionSource.MANUAL,
    )
    db_session.refresh(strategy)
    return strategy


def test_sell_proceeds_fund_a_same_cycle_buy(db_session):
    """AAPL is held at a 50% loss (stop_loss_pct=3 -- well past
    threshold) with cash too low, on its own, to cover NVDA's BUY.
    Only after the SELL's proceeds land does NVDA's $100 request fit:
    pre-SELL cash is $50, which alone could never cover a $100 buy."""
    aapl_rule = _asset_rule(
        "AAPL", buy_threshold=-1,  # never true; AAPL is held, so evaluate_exit runs, not evaluate_strategy
        capital={"type": "fixed_capital", "capital_usd": 1},
    )
    nvda_rule = _asset_rule(
        "NVDA", buy_threshold=ALWAYS_TRIGGERS_BUY,
        capital={"type": "fixed_capital", "capital_usd": 100},
    )
    strategy = _create_strategy(db_session, [aapl_rule, nvda_rule])

    market_data = FakeMarketDataProvider({
        "AAPL": _flat_bars("AAPL", price=50.0),
        "NVDA": _flat_bars("NVDA", price=30.0),
    })
    broker = FakeBroker(
        cash=50.0,
        positions={"AAPL": Position(symbol="AAPL", quantity=10, average_entry_price=100.0, current_price=50.0)},
        prices={"AAPL": 50.0, "NVDA": 30.0},
    )

    run_evaluation_cycle(
        db_session, strategy=strategy, strategy_version=strategy.current_version,
        market_data=market_data, broker=broker,
    )

    sells = [o for o in broker.placed_orders if o.side == OrderSide.SELL]
    buys = [o for o in broker.placed_orders if o.side == OrderSide.BUY]
    assert len(sells) == 1 and sells[0].symbol == "AAPL"
    assert len(buys) == 1 and buys[0].symbol == "NVDA"

    logs = trading_cycle_service.list_decision_logs(db_session, strategy_version_id=strategy.current_version_id)
    nvda_log = next(entry for entry in logs if entry.market_snapshot_json["symbol"] == "NVDA")
    assert nvda_log.plan_outcome == "selected"
    assert nvda_log.risk_approved is True

    aapl_log = next(entry for entry in logs if entry.market_snapshot_json["symbol"] == "AAPL")
    assert aapl_log.plan_outcome is None  # SELLs never reach the planner
    assert aapl_log.action_taken == "sell"

    # cash: 50 (start) + 500 (AAPL proceeds: 10 * $50) - 100 (NVDA buy) = 450
    assert broker.portfolio.cash == 450.0

    snapshots = trading_cycle_service.list_portfolio_snapshots(db_session, strategy_id=strategy.id)
    assert len(snapshots) == 1


def test_competing_buys_fifo_outcome_persists_end_to_end(db_session):
    """Empty portfolio -> correlation undefined for both -> FIFO by
    created_at decides. max_allocation_pct=20 is the deliberate
    scarcity lever: each candidate wants 15% of total value, so a
    second one would push total deployment to 30%, over the cap."""
    rule_early = _asset_rule(
        "SYM1", buy_threshold=ALWAYS_TRIGGERS_BUY,
        capital={"type": "percentage_of_portfolio", "percentage": 15},
        created_at="2026-01-01T00:00:00+00:00",
    )
    rule_later = _asset_rule(
        "SYM2", buy_threshold=ALWAYS_TRIGGERS_BUY,
        capital={"type": "percentage_of_portfolio", "percentage": 15},
        created_at="2026-01-02T00:00:00+00:00",
    )
    strategy = _create_strategy(
        db_session, [rule_early, rule_later],
        portfolio_rules={"cash_reserve_pct": 0, "max_allocation_pct": 20,
                          "max_open_positions": None, "total_capital_usd": None},
    )

    market_data = FakeMarketDataProvider({
        "SYM1": _flat_bars("SYM1", price=50.0),
        "SYM2": _flat_bars("SYM2", price=50.0),
    })
    broker = FakeBroker(cash=1000.0, prices={"SYM1": 50.0, "SYM2": 50.0})

    run_evaluation_cycle(
        db_session, strategy=strategy, strategy_version=strategy.current_version,
        market_data=market_data, broker=broker,
    )

    assert len(broker.placed_orders) == 1
    assert broker.placed_orders[0].symbol == "SYM1"

    logs = trading_cycle_service.list_decision_logs(db_session, strategy_version_id=strategy.current_version_id)
    assert len(logs) == 2
    sym1_log = next(entry for entry in logs if entry.market_snapshot_json["symbol"] == "SYM1")
    sym2_log = next(entry for entry in logs if entry.market_snapshot_json["symbol"] == "SYM2")

    assert sym1_log.plan_outcome == "selected"
    assert sym1_log.risk_approved is True
    assert sym2_log.plan_outcome == "deferred"
    assert sym2_log.risk_approved is False


def test_liquidity_infeasible_candidate_never_reaches_risk_manager(db_session):
    """volume=1000 -> ADV=1000 -> max feasible capital = 1000 * 0.01 *
    $50 = $500. Requesting $5000 should be skipped before any risk
    check, regardless of how much cash is available."""
    rule = _asset_rule(
        "THIN", buy_threshold=ALWAYS_TRIGGERS_BUY,
        capital={"type": "fixed_capital", "capital_usd": 5000},
    )
    strategy = _create_strategy(db_session, [rule])

    market_data = FakeMarketDataProvider({"THIN": _flat_bars("THIN", price=50.0, volume=1000.0)})
    broker = FakeBroker(cash=100_000.0, prices={"THIN": 50.0})

    run_evaluation_cycle(
        db_session, strategy=strategy, strategy_version=strategy.current_version,
        market_data=market_data, broker=broker,
    )

    assert len(broker.placed_orders) == 0

    logs = trading_cycle_service.list_decision_logs(db_session, strategy_version_id=strategy.current_version_id)
    assert len(logs) == 1
    assert logs[0].plan_outcome == "skipped_liquidity"
    assert logs[0].risk_approved is False
    assert "average daily volume" in logs[0].risk_reason


def test_anticorrelated_candidate_preferred_over_correlated_one(db_session):
    """TECH1 is held (no asset_rule -- never evaluated for exit,
    exists only as a correlation reference). TECH2 moves identically
    to TECH1 (+1 correlation); SAFE's returns are the exact negation
    of TECH1's (-1 correlation), built programmatically rather than
    hand-derived. Capital covers only one $250 buy on top of the
    existing $1000 TECH1 position (max_allocation_pct=100 -> cap is
    the portfolio's own total value, $1300 -- funding both would
    require $1500). SAFE should be selected, TECH2 deferred."""
    tech1_closes = [100.0 + i for i in range(25)]
    tech2_closes = [c + 5 for c in tech1_closes]  # parallel shift: identical shape, +1 correlation
    safe_closes = _negated_returns_series(tech1_closes, start_price=50.0)  # exact -1 correlation

    tech2_rule = _asset_rule(
        "TECH2", buy_threshold=ALWAYS_TRIGGERS_BUY,
        capital={"type": "fixed_capital", "capital_usd": 250},
    )
    safe_rule = _asset_rule(
        "SAFE", buy_threshold=ALWAYS_TRIGGERS_BUY,
        capital={"type": "fixed_capital", "capital_usd": 250},
    )
    strategy = _create_strategy(
        db_session, [tech2_rule, safe_rule],
        portfolio_rules={"cash_reserve_pct": 0, "max_allocation_pct": 100,
                          "max_open_positions": None, "total_capital_usd": None},
    )

    market_data = FakeMarketDataProvider({
        "TECH1": _bars_from_closes("TECH1", tech1_closes),
        "TECH2": _bars_from_closes("TECH2", tech2_closes),
        "SAFE": _bars_from_closes("SAFE", safe_closes),
    })
    broker = FakeBroker(
        cash=300.0,
        positions={"TECH1": Position(symbol="TECH1", quantity=10, average_entry_price=100.0, current_price=100.0)},
        prices={"TECH2": tech2_closes[-1], "SAFE": safe_closes[-1]},
    )

    run_evaluation_cycle(
        db_session, strategy=strategy, strategy_version=strategy.current_version,
        market_data=market_data, broker=broker,
    )

    assert len(broker.placed_orders) == 1
    assert broker.placed_orders[0].symbol == "SAFE"

    logs = trading_cycle_service.list_decision_logs(db_session, strategy_version_id=strategy.current_version_id)
    safe_log = next(entry for entry in logs if entry.market_snapshot_json["symbol"] == "SAFE")
    tech2_log = next(entry for entry in logs if entry.market_snapshot_json["symbol"] == "TECH2")

    assert safe_log.plan_outcome == "selected"
    assert safe_log.risk_approved is True
    assert tech2_log.plan_outcome == "deferred"