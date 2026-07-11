"""Unit tests for evaluate_risk."""

from datetime import datetime, timezone

from app.schemas.strategy import ConditionGroup, ExitRules, PositionSizing, RuleCondition, StrategyConfig
from app.trading_engine.domain.portfolio import Portfolio
from app.trading_engine.domain.position import Position
from app.trading_engine.domain.signal import Signal, SignalAction
from app.trading_engine.risk.risk_limits import RiskLimits
from app.trading_engine.risk.risk_manager import evaluate_risk


def _config(value_pct: float = 5) -> StrategyConfig:
    return StrategyConfig(
        symbol="AAPL",
        conditions=ConditionGroup(
            operator="AND",
            rules=[RuleCondition(indicator="RSI", period=14, operator="less_than", value=30)],
        ),
        position_sizing=PositionSizing(type="fixed_allocation", value_pct=value_pct),
        exit=ExitRules(stop_loss_pct=3, take_profit_pct=None),
    )


def _buy_signal(evaluated: bool = True) -> Signal:
    return Signal(
        symbol="AAPL",
        action=SignalAction.BUY,
        timestamp=datetime.now(timezone.utc),
        evaluated=evaluated,
        triggered_rules=["RSI(14) < 30"],
    )


def test_non_buy_signal_is_rejected():
    signal = Signal(
        symbol="AAPL", action=SignalAction.HOLD,
        timestamp=datetime.now(timezone.utc), evaluated=True,
    )
    portfolio = Portfolio(cash=10000.0)

    decision = evaluate_risk(signal, portfolio, _config(), RiskLimits(), current_price=100.0)

    assert decision.approved is False
    assert "not a BUY" in decision.reason


def test_unevaluated_signal_is_rejected():
    signal = _buy_signal(evaluated=False)
    portfolio = Portfolio(cash=10000.0)

    decision = evaluate_risk(signal, portfolio, _config(), RiskLimits(), current_price=100.0)

    assert decision.approved is False
    assert "insufficient data" in decision.reason


def test_normal_buy_within_limits_is_approved():
    signal = _buy_signal()
    portfolio = Portfolio(cash=10000.0)

    decision = evaluate_risk(signal, portfolio, _config(value_pct=5), RiskLimits(), current_price=100.0)

    assert decision.approved is True
    assert decision.quantity == 5.0  # 5% of 10000 = 500, / 100 price = 5 shares


def test_position_exceeding_max_position_pct_is_rejected():
    signal = _buy_signal()
    portfolio = Portfolio(cash=10000.0)
    limits = RiskLimits(max_position_pct=0.02)  # very tight cap

    decision = evaluate_risk(signal, portfolio, _config(value_pct=5), limits, current_price=100.0)

    assert decision.approved is False
    assert "max_position_pct" in decision.reason


def test_existing_position_counts_toward_max_position_pct():
    signal = _buy_signal()
    portfolio = Portfolio(
        cash=8000.0,
        positions={"AAPL": Position(symbol="AAPL", quantity=15, average_entry_price=100.0, current_price=100.0)},
    )
    # total_value = 8000 + 1500 = 9500; existing position already 1500 (~15.8%)
    limits = RiskLimits(max_position_pct=0.20)

    decision = evaluate_risk(signal, portfolio, _config(value_pct=10), limits, current_price=100.0)

    assert decision.approved is False
    assert "max_position_pct" in decision.reason


def test_deployment_exceeding_max_portfolio_deployment_pct_is_rejected():
    signal = _buy_signal()
    portfolio = Portfolio(
        cash=2000.0,
        positions={"TSLA": Position(symbol="TSLA", quantity=10, average_entry_price=750.0, current_price=750.0)},
    )
    # total_value = 2000 + 7500 = 9500; already ~79% deployed
    limits = RiskLimits(max_portfolio_deployment_pct=0.80, max_position_pct=1.0)

    decision = evaluate_risk(signal, portfolio, _config(value_pct=5), limits, current_price=100.0)

    assert decision.approved is False
    assert "max_portfolio_deployment_pct" in decision.reason


def test_min_cash_reserve_violation_is_rejected():
    signal = _buy_signal()
    portfolio = Portfolio(cash=1000.0)
    limits = RiskLimits(min_cash_reserve_pct=0.90, max_position_pct=1.0, max_portfolio_deployment_pct=1.0)

    decision = evaluate_risk(signal, portfolio, _config(value_pct=50), limits, current_price=100.0)

    assert decision.approved is False
    assert "min_cash_reserve_pct" in decision.reason


def test_cash_shortfall_is_caught_by_min_cash_reserve_check():
    signal = _buy_signal()
    portfolio = Portfolio(cash=100.0)
    limits = RiskLimits(max_position_pct=1.0, max_portfolio_deployment_pct=1.0, min_cash_reserve_pct=0.05)

    # total_value = cash = 100 (no positions). value_pct=100 requests all
    # 100 of it, leaving remaining_cash_after = 0, which falls below the
    # 5% reserve floor (5.0) — this is the only way cash insufficiency
    # is reachable, confirming the earlier dead-code removal was correct.
    decision = evaluate_risk(signal, portfolio, _config(value_pct=100), limits, current_price=1.5)

    assert decision.approved is False
    assert "min_cash_reserve_pct" in decision.reason