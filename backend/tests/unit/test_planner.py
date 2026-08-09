"""Unit tests for build_execution_plan — the Opportunity Engine's
planning orchestration."""

from datetime import datetime, timedelta, timezone

from app.schemas.strategy import (
    AssetRule,
    CapitalAllocation,
    ConditionGroup,
    ExitRules,
    RuleCondition,
)
from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.domain.portfolio import Portfolio
from app.trading_engine.domain.position import Position
from app.trading_engine.domain.signal import Signal, SignalAction
from app.trading_engine.opportunity.planner import build_execution_plan
from app.trading_engine.opportunity.types import Opportunity, PlanOutcome
from app.trading_engine.risk.risk_limits import RiskLimits


def _bars_from_closes(closes: list[float], symbol: str, volume: float = 100_000) -> list[MarketBar]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        MarketBar(symbol=symbol, timestamp=base + timedelta(days=i),
                  open=c, high=c, low=c, close=c, volume=volume)
        for i, c in enumerate(closes)
    ]


def _rule(symbol: str, created_at: datetime, capital_usd: float) -> AssetRule:
    """fixed_capital, matching whatever dollar amount the test scenario
    intends -- unlike percentage_of_portfolio, this never silently
    drifts as the simulated portfolio's total_value changes during
    planning, so test numbers mean exactly what they say."""
    return AssetRule(
        symbol=symbol, created_at=created_at, updated_at=created_at,
        buy_conditions=ConditionGroup(operator="AND", rules=[
            RuleCondition(indicator="RSI", period=14, operator="less_than", value=30)
        ]),
        sell_conditions=ConditionGroup(operator="AND", rules=[]),
        capital_allocation=CapitalAllocation(type="fixed_capital", capital_usd=capital_usd),
        exit=ExitRules(),
    )


def _opportunity(symbol: str, created_at: datetime, requested_capital: float, price: float = 100.0) -> Opportunity:
    rule = _rule(symbol, created_at, capital_usd=requested_capital)
    signal = Signal(
        symbol=symbol, action=SignalAction.BUY, timestamp=created_at,
        evaluated=True, triggered_rules=[f"RSI(14) < 30 for {symbol}"],
    )
    return Opportunity(
        symbol=symbol, rule=rule, signal=signal,
        current_price=price, requested_capital=requested_capital,
    )


def test_single_opportunity_within_all_limits_is_planned():
    portfolio = Portfolio(cash=10000.0)
    opp = _opportunity("AAPL", datetime(2026, 1, 1, tzinfo=timezone.utc), requested_capital=1000.0)
    bars = {"AAPL": _bars_from_closes([100.0] * 25, "AAPL")}

    plan = build_execution_plan([opp], portfolio, bars, RiskLimits())

    assert len(plan.selected) == 1
    assert plan.entries[0].outcome == PlanOutcome.SELECTED


def test_liquidity_infeasible_opportunity_is_skipped_before_ranking():
    portfolio = Portfolio(cash=1_000_000.0)
    opp = _opportunity("THIN", datetime(2026, 1, 1, tzinfo=timezone.utc), requested_capital=500_000.0)
    bars = {"THIN": _bars_from_closes([100.0] * 25, "THIN", volume=1000)}  # tiny ADV

    plan = build_execution_plan([opp], portfolio, bars, RiskLimits())

    assert len(plan.entries) == 1
    assert plan.entries[0].outcome == PlanOutcome.SKIPPED_LIQUIDITY
    assert plan.entries[0].order_in_plan is None


def test_insufficient_capital_defers_second_candidate():
    portfolio = Portfolio(cash=1500.0)
    early = datetime(2026, 1, 1, tzinfo=timezone.utc)
    later = datetime(2026, 1, 2, tzinfo=timezone.utc)
    opp1 = _opportunity("AAPL", early, requested_capital=1000.0)
    opp2 = _opportunity("NVDA", later, requested_capital=1000.0)
    bars = {
        "AAPL": _bars_from_closes([100.0] * 25, "AAPL"),
        "NVDA": _bars_from_closes([100.0] * 25, "NVDA"),
    }
    limits = RiskLimits(max_position_pct=1.0, max_portfolio_deployment_pct=1.0, min_cash_reserve_pct=0.0)

    plan = build_execution_plan([opp1, opp2], portfolio, bars, limits)

    outcomes = {e.opportunity.symbol: e.outcome for e in plan.entries}
    assert outcomes["AAPL"] == PlanOutcome.SELECTED
    assert outcomes["NVDA"] == PlanOutcome.DEFERRED


def test_fifo_tiebreak_when_no_correlation_evidence_exists():
    """Empty portfolio -> neither candidate has anything to correlate
    against -> both fall to the FIFO tier -> the earlier-created rule
    is considered (and funded) first."""
    portfolio = Portfolio(cash=10000.0)
    early = datetime(2026, 1, 1, tzinfo=timezone.utc)
    later = datetime(2026, 1, 2, tzinfo=timezone.utc)
    opp_later = _opportunity("NVDA", later, requested_capital=500.0)
    opp_early = _opportunity("AAPL", early, requested_capital=500.0)
    bars = {
        "AAPL": _bars_from_closes([100.0] * 25, "AAPL"),
        "NVDA": _bars_from_closes([100.0] * 25, "NVDA"),
    }

    # Pass in reverse-creation order deliberately, to prove ordering
    # comes from created_at, not list position.
    plan = build_execution_plan([opp_later, opp_early], portfolio, bars, RiskLimits())

    first_considered = min(plan.entries, key=lambda e: e.order_in_plan or 0)
    assert first_considered.opportunity.symbol == "AAPL"


def test_less_correlated_candidate_is_preferred_when_capital_is_scarce():
    """Existing holding TECH1 is highly correlated with candidate
    TECH2 and anti-correlated with candidate SAFE. Capital only covers
    one new $500 position -- SAFE should be preferred and funded,
    TECH2 deferred. Uses explicit permissive limits (matching
    test_insufficient_capital_defers_second_candidate's pattern) so
    the scenario tests correlation preference specifically, not an
    incidental interaction with the default cash-reserve floor against
    a total_value inflated by TECH1's existing position."""
    rising = [100 + i for i in range(25)]
    falling = [200 - i for i in range(25)]

    portfolio = Portfolio(
        cash=500.0,
        positions={"TECH1": Position(symbol="TECH1", quantity=10, average_entry_price=100.0, current_price=124.0)},
    )
    early = datetime(2026, 1, 1, tzinfo=timezone.utc)
    opp_tech2 = _opportunity("TECH2", early, requested_capital=500.0)
    opp_safe = _opportunity("SAFE", early, requested_capital=500.0)
    bars = {
        "TECH1": _bars_from_closes(rising, "TECH1"),
        "TECH2": _bars_from_closes(rising, "TECH2"),     # correlated with TECH1
        "SAFE": _bars_from_closes(falling, "SAFE"),      # anti-correlated with TECH1
    }
    limits = RiskLimits(max_position_pct=1.0, max_portfolio_deployment_pct=1.0, min_cash_reserve_pct=0.0)

    plan = build_execution_plan([opp_tech2, opp_safe], portfolio, bars, limits)

    outcomes = {e.opportunity.symbol: e.outcome for e in plan.entries}
    assert outcomes["SAFE"] == PlanOutcome.SELECTED
    assert outcomes["TECH2"] == PlanOutcome.DEFERRED