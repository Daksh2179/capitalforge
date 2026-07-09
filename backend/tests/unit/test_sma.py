"""Unit tests for calculate_sma."""

from datetime import datetime, timedelta, timezone

from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.indicators.sma import calculate_sma


def _bars_from_closes(closes: list[float]) -> list[MarketBar]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        MarketBar(
            symbol="TEST",
            timestamp=base + timedelta(days=i),
            open=c,
            high=c,
            low=c,
            close=c,
            volume=0.0,
        )
        for i, c in enumerate(closes)
    ]


def test_sma_normal_calculation():
    # closes: 1..10, SMA(3) at index 2 = avg(1,2,3) = 2.0
    bars = _bars_from_closes([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    result = calculate_sma(bars, period=3)

    assert result[2] == 2.0
    assert result[3] == 3.0
    assert result[9] == 9.0  # avg(8,9,10)


def test_sma_insufficient_history_returns_none():
    bars = _bars_from_closes([1, 2, 3, 4, 5])
    result = calculate_sma(bars, period=10)

    assert result == [None, None, None, None, None]


def test_sma_first_valid_index_is_period_minus_one():
    bars = _bars_from_closes([1, 2, 3, 4, 5])
    result = calculate_sma(bars, period=3)

    assert result[0] is None
    assert result[1] is None
    assert result[2] == 2.0  # avg(1,2,3)


def test_sma_result_length_matches_input_length():
    bars = _bars_from_closes([1, 2, 3, 4, 5, 6, 7])
    result = calculate_sma(bars, period=4)

    assert len(result) == len(bars)