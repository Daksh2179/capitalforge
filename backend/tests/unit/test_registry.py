"""Unit tests for the indicator registry."""

from datetime import datetime, timedelta, timezone

import pytest

from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.indicators.ema import calculate_ema
from app.trading_engine.indicators.registry import resolve_indicator
from app.trading_engine.indicators.rsi import calculate_rsi
from app.trading_engine.indicators.sma import calculate_sma


def test_resolve_indicator_returns_correct_function():
    assert resolve_indicator("RSI") is calculate_rsi
    assert resolve_indicator("SMA") is calculate_sma
    assert resolve_indicator("EMA") is calculate_ema


def test_resolve_indicator_raises_on_unknown_name():
    with pytest.raises(ValueError):
        resolve_indicator("MACD")


def test_resolved_indicator_is_callable_against_bars():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = [
        MarketBar(
            symbol="TEST", timestamp=base + timedelta(days=i),
            open=float(i + 1), high=float(i + 1), low=float(i + 1),
            close=float(i + 1), volume=0.0,
        )
        for i in range(5)
    ]
    result = resolve_indicator("SMA")(bars, 3)
    assert len(result) == 5