"""Unit tests for evaluate_strategy and evaluate_exit."""

from datetime import datetime, timedelta, timezone

from app.schemas.strategy import AssetRule, CapitalAllocation, ConditionGroup, ExitRules, RuleCondition
from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.domain.position import Position
from app.trading_engine.domain.signal import SignalAction
from app.trading_engine.rules.evaluator import evaluate_exit, evaluate_strategy


def _bars_from_closes(closes: list[float], highs: list[float] | None = None) -> list[MarketBar]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    highs = highs or closes
    return [
        MarketBar(symbol="TEST", timestamp=base + timedelta(days=i),
                   open=c, high=h, low=c, close=c, volume=0.0)
        for i, (c, h) in enumerate(zip(closes, highs))
    ]


def _never_true_group() -> ConditionGroup:
    return ConditionGroup(
        operator="AND",
        rules=[RuleCondition(indicator="PRICE", period=1, operator="greater_than", value=999999999)],
    )


def _rule(
    buy_conditions: ConditionGroup,
    sell_conditions: ConditionGroup | None = None,
    stop_loss_pct: float | None = None,
    take_profit_pct: float | None = None,
) -> AssetRule:
    return AssetRule(
        symbol="TEST",
        buy_conditions=buy_conditions,
        sell_conditions=sell_conditions or _never_true_group(),
        capital_allocation=CapitalAllocation(type="percentage_of_portfolio", percentage=5),
        exit=ExitRules(stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct),
    )


def test_insufficient_data_returns_unevaluated_hold():
    bars = _bars_from_closes([1, 2, 3, 4, 5])  # RSI(14) needs 15 bars
    rule = _rule(
        buy_conditions=ConditionGroup(
            operator="AND",
            rules=[RuleCondition(indicator="RSI", period=14, operator="less_than", value=30)],
        )
    )

    signal = evaluate_strategy(bars, rule)

    assert signal.evaluated is False
    assert signal.action == SignalAction.HOLD
    assert signal.triggered_rules == []


def test_single_rule_true_produces_buy():
    closes = [float(i) for i in range(20, 0, -1)]
    bars = _bars_from_closes(closes)
    rule = _rule(
        buy_conditions=ConditionGroup(
            operator="AND",
            rules=[RuleCondition(indicator="RSI", period=14, operator="less_than", value=30)],
        )
    )

    signal = evaluate_strategy(bars, rule)

    assert signal.evaluated is True
    assert signal.action == SignalAction.BUY
    assert len(signal.triggered_rules) == 1


def test_single_rule_false_produces_hold():
    closes = [float(i) for i in range(1, 21)]
    bars = _bars_from_closes(closes)
    rule = _rule(
        buy_conditions=ConditionGroup(
            operator="AND",
            rules=[RuleCondition(indicator="RSI", period=14, operator="less_than", value=30)],
        )
    )

    signal = evaluate_strategy(bars, rule)

    assert signal.evaluated is True
    assert signal.action == SignalAction.HOLD
    assert signal.triggered_rules == []


def test_and_group_fails_if_any_rule_false():
    closes = [float(i) for i in range(1, 21)]
    bars = _bars_from_closes(closes)
    rule = _rule(
        buy_conditions=ConditionGroup(
            operator="AND",
            rules=[
                RuleCondition(indicator="SMA", period=5, operator="price_above"),
                RuleCondition(indicator="RSI", period=14, operator="less_than", value=30),
            ],
        )
    )

    signal = evaluate_strategy(bars, rule)

    assert signal.evaluated is True
    assert signal.action == SignalAction.HOLD


def test_or_group_true_if_any_rule_true():
    closes = [float(i) for i in range(1, 21)]
    bars = _bars_from_closes(closes)
    rule = _rule(
        buy_conditions=ConditionGroup(
            operator="OR",
            rules=[
                RuleCondition(indicator="SMA", period=5, operator="price_above"),
                RuleCondition(indicator="RSI", period=14, operator="less_than", value=30),
            ],
        )
    )

    signal = evaluate_strategy(bars, rule)

    assert signal.evaluated is True
    assert signal.action == SignalAction.BUY
    assert len(signal.triggered_rules) == 1


def test_price_below_operator():
    closes = [float(i) for i in range(20, 0, -1)]
    bars = _bars_from_closes(closes)
    rule = _rule(
        buy_conditions=ConditionGroup(
            operator="AND",
            rules=[RuleCondition(indicator="SMA", period=5, operator="price_below")],
        )
    )

    signal = evaluate_strategy(bars, rule)

    assert signal.evaluated is True
    assert signal.action == SignalAction.BUY


def test_indicator_vs_indicator_greater_than():
    closes = [float(i) for i in range(1, 21)]
    bars = _bars_from_closes(closes)
    rule = _rule(
        buy_conditions=ConditionGroup(
            operator="AND",
            rules=[RuleCondition(
                indicator="EMA", period=3, operator="greater_than",
                compare_indicator="SMA", compare_period=10,
            )],
        )
    )

    signal = evaluate_strategy(bars, rule)

    assert signal.evaluated is True
    assert signal.action == SignalAction.BUY


def test_crosses_above_indicator_vs_indicator():
    # Hand-verified: SMA(2) vs SMA(4).
    # closes: 10, 10, 10, 9, 100
    # SMA4 @ idx3 = avg(10,10,10,9) = 9.75; SMA2 @ idx3 = avg(10,9) = 9.5 -> fast strictly BELOW slow
    # SMA4 @ idx4 = avg(10,10,9,100) = 32.25; SMA2 @ idx4 = avg(9,100) = 54.5 -> fast strictly ABOVE slow
    # -> genuine below-to-above crossover at idx4, no tie.
    closes = [10.0, 10.0, 10.0, 9.0, 100.0]
    bars = _bars_from_closes(closes)
    rule = _rule(
        buy_conditions=ConditionGroup(
            operator="AND",
            rules=[RuleCondition(
                indicator="SMA", period=2, operator="crosses_above",
                compare_indicator="SMA", compare_period=4,
            )],
        )
    )

    signal = evaluate_strategy(bars, rule)

    assert signal.evaluated is True
    assert signal.action == SignalAction.BUY


def test_pct_below_operator():
    highs = [100.0] * 10
    closes = [100.0] * 9 + [90.0]
    bars = _bars_from_closes(closes, highs=highs)
    rule = _rule(
        buy_conditions=ConditionGroup(
            operator="AND",
            rules=[RuleCondition(indicator="ROLLING_HIGH", period=5, operator="pct_below", value=5)],
        )
    )

    signal = evaluate_strategy(bars, rule)

    assert signal.evaluated is True
    assert signal.action == SignalAction.BUY


def test_evaluate_exit_stop_loss_triggers_sell():
    position = Position(symbol="TEST", quantity=10, average_entry_price=100.0)
    bars = _bars_from_closes([96.0])
    rule = _rule(
        buy_conditions=ConditionGroup(
            operator="AND",
            rules=[RuleCondition(indicator="RSI", period=14, operator="less_than", value=30)],
        ),
        stop_loss_pct=3,
    )

    signal = evaluate_exit(position, bars, rule)

    assert signal.action == SignalAction.SELL
    assert signal.evaluated is True
    assert any("stop_loss" in r for r in signal.triggered_rules)


def test_evaluate_exit_no_trigger_returns_hold():
    position = Position(symbol="TEST", quantity=10, average_entry_price=100.0)
    bars = _bars_from_closes([101.0])
    rule = _rule(
        buy_conditions=ConditionGroup(
            operator="AND",
            rules=[RuleCondition(indicator="RSI", period=14, operator="less_than", value=30)],
        ),
        stop_loss_pct=3,
    )

    signal = evaluate_exit(position, bars, rule)

    assert signal.action == SignalAction.HOLD
    assert signal.evaluated is True
    assert signal.triggered_rules == []


def test_evaluate_exit_with_no_percentage_net_relies_on_sell_conditions():
    position = Position(symbol="TEST", quantity=10, average_entry_price=100.0)
    bars = _bars_from_closes([50.0])  # huge drop, but no percentage exit configured
    rule = _rule(
        buy_conditions=ConditionGroup(
            operator="AND",
            rules=[RuleCondition(indicator="RSI", period=14, operator="less_than", value=30)],
        ),
        # sell_conditions defaults to _never_true_group(), always evaluable via PRICE
        # no stop_loss_pct/take_profit_pct configured
    )

    signal = evaluate_exit(position, bars, rule)

    assert signal.action == SignalAction.HOLD
    assert signal.evaluated is True  # sell_conditions (PRICE-based) was checked and found false