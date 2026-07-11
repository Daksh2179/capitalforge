"""Unit tests for evaluate_strategy."""

from datetime import datetime, timedelta, timezone

from app.schemas.strategy import ConditionGroup, ExitRules, PositionSizing, RuleCondition, StrategyConfig
from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.domain.signal import SignalAction
from app.trading_engine.rules.evaluator import evaluate_strategy


def _bars_from_closes(closes: list[float]) -> list[MarketBar]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        MarketBar(
            symbol="TEST", timestamp=base + timedelta(days=i),
            open=c, high=c, low=c, close=c, volume=0.0,
        )
        for i, c in enumerate(closes)
    ]


def _config(conditions: ConditionGroup) -> StrategyConfig:
    return StrategyConfig(
        symbol="TEST",
        conditions=conditions,
        position_sizing=PositionSizing(type="fixed_allocation", value_pct=5),
        exit=ExitRules(stop_loss_pct=3, take_profit_pct=None),
    )


def test_insufficient_data_returns_unevaluated_hold():
    bars = _bars_from_closes([1, 2, 3, 4, 5])  # RSI(14) needs 15 bars
    config = _config(
        ConditionGroup(
            operator="AND",
            rules=[RuleCondition(indicator="RSI", period=14, operator="less_than", value=30)],
        )
    )

    signal = evaluate_strategy(bars, config)

    assert signal.evaluated is False
    assert signal.action == SignalAction.HOLD
    assert signal.triggered_rules == []


def test_single_rule_true_produces_buy():
    closes = [float(i) for i in range(20, 0, -1)]  # strictly decreasing -> RSI(14) == 0
    bars = _bars_from_closes(closes)
    config = _config(
        ConditionGroup(
            operator="AND",
            rules=[RuleCondition(indicator="RSI", period=14, operator="less_than", value=30)],
        )
    )

    signal = evaluate_strategy(bars, config)

    assert signal.evaluated is True
    assert signal.action == SignalAction.BUY
    assert len(signal.triggered_rules) == 1


def test_single_rule_false_produces_hold():
    closes = [float(i) for i in range(1, 21)]  # strictly increasing -> RSI(14) == 100
    bars = _bars_from_closes(closes)
    config = _config(
        ConditionGroup(
            operator="AND",
            rules=[RuleCondition(indicator="RSI", period=14, operator="less_than", value=30)],
        )
    )

    signal = evaluate_strategy(bars, config)

    assert signal.evaluated is True
    assert signal.action == SignalAction.HOLD
    assert signal.triggered_rules == []


def test_and_group_fails_if_any_rule_false():
    closes = [float(i) for i in range(1, 21)]  # increasing -> price_above True, RSI<30 False
    bars = _bars_from_closes(closes)
    config = _config(
        ConditionGroup(
            operator="AND",
            rules=[
                RuleCondition(indicator="SMA", period=5, operator="price_above"),
                RuleCondition(indicator="RSI", period=14, operator="less_than", value=30),
            ],
        )
    )

    signal = evaluate_strategy(bars, config)

    assert signal.evaluated is True
    assert signal.action == SignalAction.HOLD


def test_or_group_true_if_any_rule_true():
    closes = [float(i) for i in range(1, 21)]
    bars = _bars_from_closes(closes)
    config = _config(
        ConditionGroup(
            operator="OR",
            rules=[
                RuleCondition(indicator="SMA", period=5, operator="price_above"),
                RuleCondition(indicator="RSI", period=14, operator="less_than", value=30),
            ],
        )
    )

    signal = evaluate_strategy(bars, config)

    assert signal.evaluated is True
    assert signal.action == SignalAction.BUY
    assert len(signal.triggered_rules) == 1  # only price_above triggered


def test_price_below_operator():
    closes = [float(i) for i in range(20, 0, -1)]  # decreasing -> close below lagging SMA
    bars = _bars_from_closes(closes)
    config = _config(
        ConditionGroup(
            operator="AND",
            rules=[RuleCondition(indicator="SMA", period=5, operator="price_below")],
        )
    )

    signal = evaluate_strategy(bars, config)

    assert signal.evaluated is True
    assert signal.action == SignalAction.BUY