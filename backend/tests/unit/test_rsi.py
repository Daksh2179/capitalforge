"""Unit tests for calculate_rsi (Wilder's method)."""

from datetime import datetime, timedelta, timezone

from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.indicators.rsi import calculate_rsi


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


def test_rsi_insufficient_history_returns_all_none():
    # period=14 needs 15 bars minimum; only 10 given.
    bars = _bars_from_closes([float(i) for i in range(1, 11)])
    result = calculate_rsi(bars, period=14)

    assert result == [None] * 10


def test_rsi_first_valid_index_is_period():
    # period+1 bars is the exact minimum; first real value at index == period.
    closes = [44, 44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84,
              46.08, 45.89, 46.03, 46.83, 47.69]  # 15 closes, period=14
    bars = _bars_from_closes(closes)
    result = calculate_rsi(bars, period=14)

    assert all(v is None for v in result[:14])
    assert result[14] is not None
    assert 0 <= result[14] <= 100


def test_rsi_all_gains_approaches_100():
    # Strictly increasing prices: avg_loss = 0 -> RSI = 100.
    closes = [float(i) for i in range(1, 17)]  # 16 increasing values, period=14
    bars = _bars_from_closes(closes)
    result = calculate_rsi(bars, period=14)

    assert result[14] == 100.0


def test_rsi_all_losses_approaches_0():
    # Strictly decreasing prices: avg_gain = 0 -> RSI = 0.
    closes = [float(i) for i in range(16, 0, -1)]  # 16 decreasing values
    bars = _bars_from_closes(closes)
    result = calculate_rsi(bars, period=14)

    assert result[14] == 0.0


def test_rsi_result_length_matches_input_length():
    closes = [float(i) for i in range(1, 20)]
    bars = _bars_from_closes(closes)
    result = calculate_rsi(bars, period=14)

    assert len(result) == len(bars)