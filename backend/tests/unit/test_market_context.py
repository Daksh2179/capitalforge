"""Unit tests for get_market_context, using a fake MarketDataProvider —
no real Alpaca calls needed."""

from datetime import datetime, timedelta, timezone

from app.agent.context.market_context import MarketContext, get_market_context
from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.market_data.provider import MarketDataProvider


class FakeMarketDataProvider(MarketDataProvider):
    def __init__(self, bars: list[MarketBar]) -> None:
        self._bars = bars

    def get_historical_bars(self, symbol, timeframe, start, end):
        return self._bars


def _bars(highs: list[float], lows: list[float], closes: list[float]) -> list[MarketBar]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        MarketBar(
            symbol="AAPL", timestamp=base + timedelta(days=i),
            open=c, high=h, low=lo, close=c, volume=0.0,
        )
        for i, (h, lo, c) in enumerate(zip(highs, lows, closes))
    ]


def test_returns_none_when_no_bars_available():
    provider = FakeMarketDataProvider([])
    result = get_market_context("AAPL", provider)

    assert result is None


def test_current_price_is_latest_close():
    bars = _bars(highs=[110, 115, 120], lows=[95, 98, 100], closes=[105, 110, 118])
    provider = FakeMarketDataProvider(bars)

    result = get_market_context("AAPL", provider)

    assert result is not None
    assert result.current_price == 118


def test_week_52_high_is_max_of_all_highs():
    bars = _bars(highs=[110, 130, 120], lows=[95, 98, 100], closes=[105, 110, 118])
    provider = FakeMarketDataProvider(bars)

    result = get_market_context("AAPL", provider)

    assert result is not None
    assert result.week_52_high == 130


def test_week_52_low_is_min_of_all_lows():
    bars = _bars(highs=[110, 115, 120], lows=[95, 80, 100], closes=[105, 110, 118])
    provider = FakeMarketDataProvider(bars)

    result = get_market_context("AAPL", provider)

    assert result is not None
    assert result.week_52_low == 80


def test_symbol_reflects_the_requested_symbol():
    bars = _bars(highs=[110], lows=[95], closes=[105])
    provider = FakeMarketDataProvider(bars)

    result = get_market_context("NVDA", provider)

    assert result is not None
    assert result.symbol == "NVDA"


def test_market_context_is_frozen():
    context = MarketContext(symbol="AAPL", current_price=100, week_52_high=110, week_52_low=90)

    try:
        context.current_price = 200  # type: ignore[misc]
        assert False, "expected FrozenInstanceError"
    except AttributeError:
        pass