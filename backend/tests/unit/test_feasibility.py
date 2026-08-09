"""Unit tests for the Opportunity Engine's liquidity feasibility check."""

from datetime import datetime, timedelta, timezone

from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.opportunity.feasibility import (
    LIQUIDITY_MAX_ADV_FRACTION,
    average_daily_volume,
    is_liquidity_feasible,
)


def _bars_with_volume(volume: float, count: int = 20) -> list[MarketBar]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        MarketBar(symbol="TEST", timestamp=base + timedelta(days=i),
                  open=100, high=100, low=100, close=100, volume=volume)
        for i in range(count)
    ]


def test_average_daily_volume_of_empty_bars_is_none():
    assert average_daily_volume([]) is None


def test_average_daily_volume_averages_the_recent_window():
    bars = _bars_with_volume(1000.0, count=20)
    assert average_daily_volume(bars) == 1000.0


def test_no_bars_is_permissive():
    feasible, reason = is_liquidity_feasible(requested_capital=1_000_000, current_price=100.0, bars=[])
    assert feasible is True
    assert "insufficient" in reason


def test_zero_volume_bars_are_permissive_not_infeasible():
    # Volume=0.0 in test fixtures elsewhere in the suite shouldn't be
    # misread as "zero liquidity, therefore always infeasible."
    bars = _bars_with_volume(0.0)
    feasible, _ = is_liquidity_feasible(requested_capital=1_000_000, current_price=100.0, bars=bars)
    assert feasible is True


def test_position_within_adv_fraction_is_feasible():
    bars = _bars_with_volume(volume=100_000)
    max_capital = 100_000 * LIQUIDITY_MAX_ADV_FRACTION * 100.0  # price=100
    feasible, _ = is_liquidity_feasible(
        requested_capital=max_capital * 0.5, current_price=100.0, bars=bars
    )
    assert feasible is True


def test_position_exceeding_adv_fraction_is_infeasible():
    bars = _bars_with_volume(volume=100_000)
    max_capital = 100_000 * LIQUIDITY_MAX_ADV_FRACTION * 100.0
    feasible, reason = is_liquidity_feasible(
        requested_capital=max_capital * 2, current_price=100.0, bars=bars
    )
    assert feasible is False
    assert "average daily volume" in reason