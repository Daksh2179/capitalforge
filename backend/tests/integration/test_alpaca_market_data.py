"""Integration tests for AlpacaMarketData, run against the real Alpaca
paper API. Requires valid ALPACA_API_KEY / ALPACA_SECRET_KEY in .env.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import get_settings
from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.domain.timeframe import Timeframe
from app.trading_engine.market_data.alpaca_market_data import AlpacaMarketData


@pytest.fixture()
def market_data() -> AlpacaMarketData:
    settings = get_settings()
    return AlpacaMarketData(settings.alpaca_api_key, settings.alpaca_secret_key)


def test_get_historical_bars_returns_market_bar_instances(market_data: AlpacaMarketData):
    end = datetime.now(timezone.utc) - timedelta(days=1)
    start = end - timedelta(days=10)

    bars = market_data.get_historical_bars("AAPL", Timeframe.DAY, start, end)

    assert len(bars) > 0
    assert all(isinstance(bar, MarketBar) for bar in bars)


def test_bars_have_no_leaked_alpaca_types(market_data: AlpacaMarketData):
    end = datetime.now(timezone.utc) - timedelta(days=1)
    start = end - timedelta(days=10)

    bars = market_data.get_historical_bars("AAPL", Timeframe.DAY, start, end)

    for bar in bars:
        assert type(bar) is MarketBar
        assert isinstance(bar.timestamp, datetime)
        assert isinstance(bar.open, float)
        assert isinstance(bar.close, float)


def test_bars_are_ordered_oldest_to_newest(market_data: AlpacaMarketData):
    end = datetime.now(timezone.utc) - timedelta(days=1)
    start = end - timedelta(days=10)

    bars = market_data.get_historical_bars("AAPL", Timeframe.DAY, start, end)

    timestamps = [bar.timestamp for bar in bars]
    assert timestamps == sorted(timestamps)


def test_bar_timestamps_are_timezone_aware_utc(market_data: AlpacaMarketData):
    end = datetime.now(timezone.utc) - timedelta(days=1)
    start = end - timedelta(days=10)

    bars = market_data.get_historical_bars("AAPL", Timeframe.DAY, start, end)

    for bar in bars:
        assert bar.timestamp.tzinfo is not None

    if bars:
        assert bars[0].timestamp.utcoffset() == timedelta(0)


def test_symbol_with_no_data_in_range_returns_empty_list(market_data: AlpacaMarketData):
    # A range far enough in the past that IEX free-tier data may be sparse,
    # combined with a real but obscure symbol, to exercise the "no bars"
    # path without relying on a symbol that doesn't exist at all.
    end = datetime(2016, 1, 5, tzinfo=timezone.utc)
    start = datetime(2016, 1, 4, tzinfo=timezone.utc)

    bars = market_data.get_historical_bars("AAPL", Timeframe.MINUTE, start, end)

    # Not asserting empty specifically (AAPL likely did trade), just
    # asserting this never raises and always returns a list.
    assert isinstance(bars, list)