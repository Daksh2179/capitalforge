"""Unit tests for calculate_ema."""

from datetime import datetime, timedelta, timezone

from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.indicators.ema import calculate_ema


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


def test_ema_seed_is_simple_average_of_first_period():
    # closes: 1,2,3,4,5 ; period=3 -> seed at index 2 = avg(1,2,3) = 2.0
    bars = _bars_from_closes([1, 2, 3, 4, 5])
    result = calculate_ema(bars, period=3)

    assert result[0] is None
    assert result[1] is None
    assert result[2] == 2.0


def test_ema_subsequent_smoothing():
    # period=3 -> multiplier = 2/(3+1) = 0.5
    # seed (index 2) = avg(1,2,3) = 2.0
    # index 3: (4 - 2.0) * 0.5 + 2.0 = 3.0
    # index 4: (5 - 3.0) * 0.5 + 3.0 = 4.0
    bars = _bars_from_closes([1, 2, 3, 4, 5])
    result = calculate_ema(bars, period=3)

    assert result[3] == 3.0
    assert result[4] == 4.0


def test_ema_insufficient_history_returns_all_none():
    bars = _bars_from_closes([1, 2, 3])
    result = calculate_ema(bars, period=10)

    assert result == [None, None, None]


def test_ema_result_length_matches_input_length():
    bars = _bars_from_closes([1, 2, 3, 4, 5, 6, 7])
    result = calculate_ema(bars, period=4)

    assert len(result) == len(bars)