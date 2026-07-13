"""Unit tests for the backtest engine, using a fake MarketDataProvider
over synthetic bars — no Alpaca dependency at all."""

from datetime import datetime, timedelta, timezone

from app.schemas.strategy import AssetRule, ConditionGroup, ExitRules, PositionSizing, RuleCondition
from app.trading_engine.backtest.engine import run_backtest
from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.market_data.provider import MarketDataProvider
from app.trading_engine.risk.risk_limits import RiskLimits


class FakeMarketDataProvider(MarketDataProvider):
    def __init__(self, bars: list[MarketBar]) -> None:
        self._bars = bars

    def get_historical_bars(self, symbol, timeframe, start, end) -> list[MarketBar]:
        return self._bars


def _bars_from_closes(closes: list[float], symbol: str = "TEST") -> list[MarketBar]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        MarketBar(symbol=symbol, timestamp=base + timedelta(days=i),
                   open=c, high=c, low=c, close=c, volume=0.0)
        for i, c in enumerate(closes)
    ]


def _never_true_group() -> ConditionGroup:
    return ConditionGroup(
        operator="AND",
        rules=[RuleCondition(indicator="PRICE", period=1, operator="greater_than", value=999999999)],
    )


def _rsi_buy_dip_rule(stop_loss_pct: float | None = 3, take_profit_pct: float | None = None) -> AssetRule:
    return AssetRule(
        symbol="TEST",
        buy_conditions=ConditionGroup(
            operator="AND",
            rules=[RuleCondition(indicator="RSI", period=14, operator="less_than", value=30)],
        ),
        sell_conditions=_never_true_group(),
        position_sizing=PositionSizing(type="fixed_allocation", value_pct=10),
        exit=ExitRules(stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct),
    )


def test_backtest_produces_equity_curve_matching_bar_count():
    closes = [float(i) for i in range(1, 21)]
    provider = FakeMarketDataProvider(_bars_from_closes(closes))
    rule = _rsi_buy_dip_rule()

    result = run_backtest(
        provider, rule,
        start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end=datetime(2026, 1, 20, tzinfo=timezone.utc),
        starting_cash=10000.0,
        risk_limits=RiskLimits(),
    )

    assert len(result.equity_curve) == 20
    assert result.starting_cash == 10000.0


def test_backtest_with_no_trades_preserves_cash():
    closes = [float(i) for i in range(1, 21)]
    provider = FakeMarketDataProvider(_bars_from_closes(closes))
    rule = _rsi_buy_dip_rule()

    result = run_backtest(
        provider, rule,
        start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end=datetime(2026, 1, 20, tzinfo=timezone.utc),
        starting_cash=10000.0,
        risk_limits=RiskLimits(),
    )

    assert len(result.trades) == 0
    assert result.ending_portfolio.cash == 10000.0


def test_backtest_executes_trade_when_condition_becomes_true():
    closes = [float(i) for i in range(30, 0, -1)]
    provider = FakeMarketDataProvider(_bars_from_closes(closes))
    rule = _rsi_buy_dip_rule()

    result = run_backtest(
        provider, rule,
        start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end=datetime(2026, 1, 30, tzinfo=timezone.utc),
        starting_cash=10000.0,
        risk_limits=RiskLimits(),
    )

    assert len(result.trades) >= 1
    assert result.ending_portfolio.cash < 10000.0


def test_backtest_respects_risk_limits():
    closes = [float(i) for i in range(30, 0, -1)]
    provider = FakeMarketDataProvider(_bars_from_closes(closes))
    rule = _rsi_buy_dip_rule()

    tight_limits = RiskLimits(max_position_pct=0.001, max_portfolio_deployment_pct=0.001)

    result = run_backtest(
        provider, rule,
        start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end=datetime(2026, 1, 30, tzinfo=timezone.utc),
        starting_cash=10000.0,
        risk_limits=tight_limits,
    )

    assert len(result.trades) == 0


def test_backtest_full_round_trip_produces_trade_pnl():
    closes = [float(i) for i in range(30, 0, -1)] + [float(i) for i in range(1, 20)]
    provider = FakeMarketDataProvider(_bars_from_closes(closes))
    rule = _rsi_buy_dip_rule(stop_loss_pct=50, take_profit_pct=5)

    result = run_backtest(
        provider, rule,
        start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end=datetime(2026, 3, 1, tzinfo=timezone.utc),
        starting_cash=10000.0,
        risk_limits=RiskLimits(),
    )

    assert len(result.trades) >= 2
    assert len(result.trade_pnls) >= 1