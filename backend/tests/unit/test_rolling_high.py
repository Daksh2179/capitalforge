"""Unit tests for calculate_rolling_high."""

from datetime import datetime, timedelta, timezone

from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.indicators.rolling_high import calculate_rolling_high


def _bars_from_highs(highs: list[float]) -> list[MarketBar]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        MarketBar(symbol="TEST", timestamp=base + timedelta(days=i),
                   open=h, high=h, low=h, close=h, volume=0.0)
        for i, h in enumerate(highs)
    ]


def test_rolling_high_normal_calculation():
    bars = _bars_from_highs([10, 20, 15, 30, 25])
    result = calculate_rolling_high(bars, period=3)

    assert result[0] is None
    assert result[1] is None
    assert result[2] == 20
    assert result[3] == 30
    assert result[4] == 30


def test_rolling_high_insufficient_history_returns_none():
    bars = _bars_from_highs([10, 20])
    result = calculate_rolling_high(bars, period=5)

    assert result == [None, None]


def test_rolling_high_result_length_matches_input():
    bars = _bars_from_highs([1, 2, 3, 4, 5, 6])
    result = calculate_rolling_high(bars, period=2)

    assert len(result) == len(bars)