"""Unit tests for get_indicator_readings."""

from datetime import datetime, timedelta, timezone

from app.agent.context.indicator_context import get_indicator_readings
from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.market_data.provider import MarketDataProvider


class FakeMarketDataProvider(MarketDataProvider):
    def __init__(self, bars_by_symbol: dict[str, list[MarketBar]]) -> None:
        self._bars_by_symbol = bars_by_symbol

    def get_historical_bars(self, symbol, timeframe, start, end):
        return self._bars_by_symbol.get(symbol, [])


def _bars(closes: list[float]) -> list[MarketBar]:
    base = datetime.now(timezone.utc) - timedelta(days=len(closes))
    return [
        MarketBar(symbol="TEST", timestamp=base + timedelta(days=i),
                  open=c, high=c, low=c, close=c, volume=100_000.0)
        for i, c in enumerate(closes)
    ]


def test_computes_requested_indicator_via_the_real_registry():
    market_data = FakeMarketDataProvider({"NVDA": _bars([100.0 + i for i in range(60)])})
    readings = get_indicator_readings("NVDA", market_data, [("SMA", 20)])

    assert len(readings) == 1
    assert readings[0].indicator == "SMA"
    assert readings[0].period == 20


def test_skips_indicator_with_insufficient_history_rather_than_erroring():
    market_data = FakeMarketDataProvider({"NVDA": _bars([100.0 + i for i in range(5)])})
    readings = get_indicator_readings("NVDA", market_data, [("SMA", 200)])

    assert readings == []


def test_unknown_indicator_name_is_skipped_not_raised():
    market_data = FakeMarketDataProvider({"NVDA": _bars([100.0] * 30)})
    readings = get_indicator_readings("NVDA", market_data, [("MACD", 12)])

    assert readings == []


def test_no_bars_at_all_returns_empty():
    readings = get_indicator_readings("NVDA", FakeMarketDataProvider({}), [("RSI", 14)])

    assert readings == []


def test_multiple_requests_return_multiple_readings():
    market_data = FakeMarketDataProvider({"NVDA": _bars([100.0 - i for i in range(30)])})
    readings = get_indicator_readings("NVDA", market_data, [("RSI", 14), ("SMA", 20)])

    indicators = {r.indicator for r in readings}
    assert indicators == {"RSI", "SMA"}