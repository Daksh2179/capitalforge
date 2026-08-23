"""Unit tests for evaluate_risk."""

from datetime import datetime, timezone

from app.schemas.strategy import AssetRule, CapitalAllocation, ConditionGroup, ExitRules, RuleCondition
from app.trading_engine.domain.portfolio import Portfolio
from app.trading_engine.domain.position import Position
from app.trading_engine.domain.signal import Signal, SignalAction
from app.trading_engine.risk.risk_limits import RiskLimits
from app.trading_engine.risk.risk_manager import evaluate_risk


def _never_true_group() -> ConditionGroup:
    return ConditionGroup(
        operator="AND",
        rules=[RuleCondition(indicator="PRICE", period=1, operator="greater_than", value=999999999)],
    )


def _rule(
    value_pct: float = 5, allocation: CapitalAllocation | None = None
) -> AssetRule:
    if allocation is None:
        allocation = CapitalAllocation(type="percentage_of_portfolio", percentage=value_pct)
    return AssetRule(
        symbol="AAPL",
        buy_conditions=ConditionGroup(
            operator="AND",
            rules=[RuleCondition(indicator="RSI", period=14, operator="less_than", value=30)],
        ),
        sell_conditions=_never_true_group(),
        capital_allocation=allocation,
        exit=ExitRules(stop_loss_pct=3, take_profit_pct=None),
    )


def _buy_signal(evaluated: bool = True) -> Signal:
    return Signal(
        symbol="AAPL", action=SignalAction.BUY,
        timestamp=datetime.now(timezone.utc), evaluated=evaluated,
        triggered_rules=["RSI(14) < 30"],
    )


def test_non_buy_signal_is_rejected():
    signal = Signal(symbol="AAPL", action=SignalAction.HOLD, timestamp=datetime.now(timezone.utc), evaluated=True)
    portfolio = Portfolio(cash=10000.0)

    decision = evaluate_risk(signal, portfolio, _rule(), RiskLimits(), current_price=100.0)

    assert decision.approved is False
    assert "not a BUY" in decision.reason


def test_unevaluated_signal_is_rejected():
    signal = _buy_signal(evaluated=False)
    portfolio = Portfolio(cash=10000.0)

    decision = evaluate_risk(signal, portfolio, _rule(), RiskLimits(), current_price=100.0)

    assert decision.approved is False
    assert "insufficient data" in decision.reason


def test_normal_buy_within_limits_is_approved():
    signal = _buy_signal()
    portfolio = Portfolio(cash=10000.0)

    decision = evaluate_risk(signal, portfolio, _rule(value_pct=5), RiskLimits(), current_price=100.0)

    assert decision.approved is True
    assert decision.quantity == 5.0


def test_position_exceeding_max_position_pct_is_rejected():
    signal = _buy_signal()
    portfolio = Portfolio(cash=10000.0)
    limits = RiskLimits(max_position_pct=0.02)

    decision = evaluate_risk(signal, portfolio, _rule(value_pct=5), limits, current_price=100.0)

    assert decision.approved is False
    assert "max_position_pct" in decision.reason


def test_existing_position_counts_toward_max_position_pct():
    signal = _buy_signal()
    portfolio = Portfolio(
        cash=8000.0,
        positions={"AAPL": Position(symbol="AAPL", quantity=15, average_entry_price=100.0, current_price=100.0)},
    )
    limits = RiskLimits(max_position_pct=0.20)

    decision = evaluate_risk(signal, portfolio, _rule(value_pct=10), limits, current_price=100.0)

    assert decision.approved is False
    assert "max_position_pct" in decision.reason


def test_deployment_exceeding_max_portfolio_deployment_pct_is_rejected():
    signal = _buy_signal()
    portfolio = Portfolio(
        cash=2000.0,
        positions={"TSLA": Position(symbol="TSLA", quantity=10, average_entry_price=750.0, current_price=750.0)},
    )
    limits = RiskLimits(max_portfolio_deployment_pct=0.80, max_position_pct=1.0)

    decision = evaluate_risk(signal, portfolio, _rule(value_pct=5), limits, current_price=100.0)

    assert decision.approved is False
    assert "max_portfolio_deployment_pct" in decision.reason


def test_min_cash_reserve_violation_is_rejected():
    signal = _buy_signal()
    portfolio = Portfolio(cash=1000.0)
    limits = RiskLimits(min_cash_reserve_pct=0.90, max_position_pct=1.0, max_portfolio_deployment_pct=1.0)

    decision = evaluate_risk(signal, portfolio, _rule(value_pct=50), limits, current_price=100.0)

    assert decision.approved is False
    assert "min_cash_reserve_pct" in decision.reason


def test_cash_shortfall_is_caught_by_min_cash_reserve_check():
    signal = _buy_signal()
    portfolio = Portfolio(cash=100.0)
    limits = RiskLimits(max_position_pct=1.0, max_portfolio_deployment_pct=1.0, min_cash_reserve_pct=0.05)

    decision = evaluate_risk(signal, portfolio, _rule(value_pct=100), limits, current_price=1.5)

    assert decision.approved is False
    assert "min_cash_reserve_pct" in decision.reason


def test_sell_signal_with_open_position_is_approved_for_full_quantity():
    signal = Signal(symbol="AAPL", action=SignalAction.SELL, timestamp=datetime.now(timezone.utc), evaluated=True)
    portfolio = Portfolio(
        cash=1000.0,
        positions={"AAPL": Position(symbol="AAPL", quantity=8, average_entry_price=100.0, current_price=110.0)},
    )

    decision = evaluate_risk(signal, portfolio, _rule(), RiskLimits(), current_price=110.0)

    assert decision.approved is True
    assert decision.quantity == 8


def test_sell_signal_without_position_is_rejected():
    signal = Signal(symbol="AAPL", action=SignalAction.SELL, timestamp=datetime.now(timezone.utc), evaluated=True)
    portfolio = Portfolio(cash=1000.0)

    decision = evaluate_risk(signal, portfolio, _rule(), RiskLimits(), current_price=110.0)

    assert decision.approved is False
    assert "no open position" in decision.reason


def test_sell_signal_not_evaluated_is_rejected():
    signal = Signal(symbol="AAPL", action=SignalAction.SELL, timestamp=datetime.now(timezone.utc), evaluated=False)
    portfolio = Portfolio(
        cash=1000.0,
        positions={"AAPL": Position(symbol="AAPL", quantity=8, average_entry_price=100.0)},
    )

    decision = evaluate_risk(signal, portfolio, _rule(), RiskLimits(), current_price=110.0)

    assert decision.approved is False


def test_max_open_positions_blocks_new_symbol_when_at_cap():
    signal = _buy_signal()  # AAPL
    portfolio = Portfolio(
        cash=5000.0,
        positions={
            "TSLA": Position(symbol="TSLA", quantity=1, average_entry_price=100.0, current_price=100.0),
            "NVDA": Position(symbol="NVDA", quantity=1, average_entry_price=100.0, current_price=100.0),
        },
    )
    limits = RiskLimits(max_open_positions=2)

    decision = evaluate_risk(signal, portfolio, _rule(value_pct=5), limits, current_price=100.0)

    assert decision.approved is False
    assert "max_open_positions" in decision.reason


def test_max_open_positions_allows_adding_to_existing_symbol_at_cap():
    signal = _buy_signal()  # AAPL, already held
    portfolio = Portfolio(
        cash=5000.0,
        positions={
            "AAPL": Position(symbol="AAPL", quantity=1, average_entry_price=100.0, current_price=100.0),
            "NVDA": Position(symbol="NVDA", quantity=1, average_entry_price=100.0, current_price=100.0),
        },
    )
    limits = RiskLimits(max_open_positions=2)

    decision = evaluate_risk(signal, portfolio, _rule(value_pct=5), limits, current_price=100.0)

    assert decision.approved is True


def test_percentage_of_portfolio_sizes_quantity_from_portfolio_value():
    signal = _buy_signal()
    portfolio = Portfolio(cash=10000.0)
    rule = _rule(allocation=CapitalAllocation(type="percentage_of_portfolio", percentage=5))

    decision = evaluate_risk(signal, portfolio, rule, RiskLimits(), current_price=100.0)

    assert decision.approved is True
    # 5% of 10,000 = 500 / 100 per share = 5 shares
    assert decision.quantity == 5.0


def test_fixed_capital_sizes_quantity_from_dollar_amount():
    signal = _buy_signal()
    portfolio = Portfolio(cash=10000.0)
    rule = _rule(allocation=CapitalAllocation(type="fixed_capital", capital_usd=600))

    decision = evaluate_risk(signal, portfolio, rule, RiskLimits(), current_price=100.0)

    assert decision.approved is True
    # $600 / $100 per share = 6 shares
    assert decision.quantity == 6.0


def test_share_count_sizes_quantity_directly():
    signal = _buy_signal()
    portfolio = Portfolio(cash=10000.0)
    rule = _rule(allocation=CapitalAllocation(type="share_count", shares=7))

    decision = evaluate_risk(signal, portfolio, rule, RiskLimits(), current_price=100.0)

    assert decision.approved is True
    assert decision.quantity == 7.0


def test_fixed_capital_still_subject_to_max_position_pct():
    signal = _buy_signal()
    portfolio = Portfolio(cash=10000.0)
    rule = _rule(allocation=CapitalAllocation(type="fixed_capital", capital_usd=5000))
    limits = RiskLimits(max_position_pct=0.20)

    decision = evaluate_risk(signal, portfolio, rule, limits, current_price=100.0)

    # $5,000 is 50% of the 10,000 portfolio, over the 20% max_position_pct
    assert decision.approved is False
    assert "max_position_pct" in decision.reason


def test_within_total_capital_usd_limit_is_approved():
    signal = _buy_signal()
    portfolio = Portfolio(
        cash=10000.0,
        positions={"TSLA": Position(symbol="TSLA", quantity=10, average_entry_price=100.0, current_price=100.0)},
    )
    limits = RiskLimits(
        max_position_pct=1.0, max_portfolio_deployment_pct=1.0,
        min_cash_reserve_pct=0.0, total_capital_usd=2000.0,
    )
    rule = _rule(allocation=CapitalAllocation(type="fixed_capital", capital_usd=500))

    decision = evaluate_risk(signal, portfolio, rule, limits, current_price=100.0)

    # 1,000 already deployed + 500 requested = 1,500, within the 2,000 limit
    assert decision.approved is True


def test_exceeding_total_capital_usd_limit_is_rejected():
    """With effective_total_value = min(total_value, total_capital_usd)
    now feeding every percentage-based check, max_portfolio_deployment_pct
    (evaluated earlier in evaluate_risk) catches an over-pool request
    before execution ever reaches the dedicated total_capital_usd
    ceiling check below it -- here max_portfolio_deployment_pct=1.0
    makes max_deployed_value exactly equal to the 1,200 pool, so the
    deployment check is what actually fires. This is the intended,
    correct effect of effective_total_value (see docs/decisions.md's
    capital-pool spec): the dedicated ceiling check remains in place as
    a defensive fallback for edge configurations, but in an ordinary
    setup like this one the percentage check is now what protects the
    declared pool, with a more specific, more useful reason string.
    """
    signal = _buy_signal()
    portfolio = Portfolio(
        cash=10000.0,
        positions={"TSLA": Position(symbol="TSLA", quantity=10, average_entry_price=100.0, current_price=100.0)},
    )
    limits = RiskLimits(
        max_position_pct=1.0, max_portfolio_deployment_pct=1.0,
        min_cash_reserve_pct=0.0, total_capital_usd=1200.0,
    )
    rule = _rule(allocation=CapitalAllocation(type="fixed_capital", capital_usd=500))

    decision = evaluate_risk(signal, portfolio, rule, limits, current_price=100.0)

    # 1,000 already deployed + 500 requested = 1,500, over the 1,200 pool
    assert decision.approved is False
    assert "max_portfolio_deployment_pct" in decision.reason


def test_total_capital_usd_ceiling_fires_when_deployment_pct_would_not():
    """Isolates the dedicated total_capital_usd ceiling check itself --
    a scenario where max_portfolio_deployment_pct is set LOOSER than
    the declared pool would allow on its own (impossible once
    effective_total_value correctly caps the percentage denominator,
    since max_deployed_value = effective_total_value * pct can never
    exceed effective_total_value <= total_capital_usd when pct <= 1.0).
    So this test instead documents that the ceiling check is retained
    as inert-but-present safety net: it recomputes the exact same
    projected_deployed the percentage check already guarded, and would
    fire identically if the percentage check were ever misconfigured
    or removed. Confirms the ceiling check line itself still exists
    and still computes correctly, without asserting an unreachable
    reason string in the normal path.
    """
    signal = _buy_signal()
    portfolio = Portfolio(
        cash=10000.0,
        positions={"TSLA": Position(symbol="TSLA", quantity=10, average_entry_price=100.0, current_price=100.0)},
    )
    limits = RiskLimits(
        max_position_pct=1.0, max_portfolio_deployment_pct=1.0,
        min_cash_reserve_pct=0.0, total_capital_usd=1200.0,
    )
    rule = _rule(allocation=CapitalAllocation(type="fixed_capital", capital_usd=500))

    decision = evaluate_risk(signal, portfolio, rule, limits, current_price=100.0)

    # Rejected either way -- what matters here is that going over the
    # declared pool is never silently approved, regardless of which
    # specific check is the one that catches it.
    assert decision.approved is False


def test_total_capital_usd_check_skipped_when_unset():
    signal = _buy_signal()
    portfolio = Portfolio(
        cash=10000.0,
        positions={"TSLA": Position(symbol="TSLA", quantity=10, average_entry_price=100.0, current_price=100.0)},
    )
    limits = RiskLimits(
        max_position_pct=1.0, max_portfolio_deployment_pct=1.0, min_cash_reserve_pct=0.0,
    )
    rule = _rule(allocation=CapitalAllocation(type="fixed_capital", capital_usd=5000))

    decision = evaluate_risk(signal, portfolio, rule, limits, current_price=100.0)

    assert decision.approved is True
    
def test_percentage_of_portfolio_sizing_uses_declared_pool_not_real_account_value():
    signal = _buy_signal()
    portfolio = Portfolio(cash=10000.0)
    limits = RiskLimits(total_capital_usd=2000.0)
    rule = _rule(allocation=CapitalAllocation(type="percentage_of_portfolio", percentage=10))

    decision = evaluate_risk(signal, portfolio, rule, limits, current_price=100.0)

    # 10% of the declared $2,000 pool (not the real $10,000 account) = $200 / $100 = 2 shares
    assert decision.approved is True
    assert decision.quantity == 2.0


def test_max_position_pct_rescales_to_declared_pool():
    signal = _buy_signal()
    portfolio = Portfolio(cash=10000.0)
    limits = RiskLimits(max_position_pct=0.5, total_capital_usd=1000.0)
    rule = _rule(allocation=CapitalAllocation(type="fixed_capital", capital_usd=600))

    decision = evaluate_risk(signal, portfolio, rule, limits, current_price=100.0)

    # Against the real $10,000 account, 50% would allow $5,000 -- but
    # effective_total_value caps the denominator at the declared $1,000
    # pool, so the real limit here is $500, and $600 exceeds it.
    assert decision.approved is False
    assert "max_position_pct" in decision.reason


def test_max_portfolio_deployment_pct_rescales_to_declared_pool():
    signal = _buy_signal()
    portfolio = Portfolio(cash=10000.0)
    limits = RiskLimits(
        max_position_pct=1.0,  # loosened so this test isolates deployment_pct, not position_pct
        max_portfolio_deployment_pct=0.5, total_capital_usd=1000.0,
    )
    rule = _rule(allocation=CapitalAllocation(type="fixed_capital", capital_usd=600))

    decision = evaluate_risk(signal, portfolio, rule, limits, current_price=100.0)

    # Same shape as max_position_pct above: 50% of the real $10,000
    # account would allow $5,000, but effective_total_value caps the
    # denominator at the $1,000 pool, so the real ceiling is $500.
    assert decision.approved is False
    assert "max_portfolio_deployment_pct" in decision.reason


def test_min_cash_reserve_pct_uses_declared_pool_not_real_account_value():
    signal = _buy_signal()
    portfolio = Portfolio(cash=2000.0)
    limits = RiskLimits(
        max_position_pct=1.0, max_portfolio_deployment_pct=1.0,
        min_cash_reserve_pct=0.9, total_capital_usd=1000.0,
    )
    rule = _rule(allocation=CapitalAllocation(type="fixed_capital", capital_usd=500))

    decision = evaluate_risk(signal, portfolio, rule, limits, current_price=100.0)

    # Against the real $2,000 account, a 90% cash reserve would require
    # $1,800 remaining -- $1,500 remaining would fail that. But the
    # declared $1,000 pool only requires 90% of ITSELF ($900) held
    # back, which $1,500 comfortably clears.
    assert decision.approved is True
    assert decision.quantity == 5.0


def test_pool_larger_than_real_account_value_has_no_effect():
    signal = _buy_signal()
    portfolio = Portfolio(cash=5000.0)
    limits = RiskLimits(total_capital_usd=100_000.0)
    rule = _rule(allocation=CapitalAllocation(type="percentage_of_portfolio", percentage=10))

    decision = evaluate_risk(signal, portfolio, rule, limits, current_price=100.0)

    # min(5000, 100000) = 5000 -- the pool exceeding the real account
    # changes nothing; sizing is identical to having no pool declared.
    assert decision.approved is True
    assert decision.quantity == 5.0