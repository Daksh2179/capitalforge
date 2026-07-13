"""Unit tests for calculate_price."""

from datetime import datetime, timedelta, timezone

from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.indicators.price import calculate_price


def _bars_from_closes(closes: list[float]) -> list[MarketBar]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        MarketBar(symbol="TEST", timestamp=base + timedelta(days=i),
                   open=c, high=c, low=c, close=c, volume=0.0)
        for i, c in enumerate(closes)
    ]


def test_calculate_price_returns_close_for_every_bar():
    bars = _bars_from_closes([100, 101, 99, 105])
    result = calculate_price(bars, period=1)

    assert result == [100, 101, 99, 105]


def test_calculate_price_never_returns_none():
    bars = _bars_from_closes([50.0])
    result = calculate_price(bars, period=14)  # period ignored, still works with 1 bar

    assert result == [50.0]


def test_calculate_price_empty_bars():
    assert calculate_price([], period=1) == []