"""AlpacaMarketData: the only file in this codebase permitted to import
alpaca-py. Translates alpaca-py's request/response objects into our own
domain types before anything leaves this module.
"""

from datetime import datetime

from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.domain.timeframe import Timeframe
from app.trading_engine.market_data.provider import MarketDataProvider

_TIMEFRAME_MAP: dict[Timeframe, TimeFrame] = {
    Timeframe.MINUTE: TimeFrame(1, TimeFrameUnit.Minute),
    Timeframe.HOUR: TimeFrame(1, TimeFrameUnit.Hour),
    Timeframe.DAY: TimeFrame.Day,
}


class AlpacaMarketData(MarketDataProvider):
    """Fetches historical bars from Alpaca's Market Data API and returns
    them as our own MarketBar objects. Uses the free IEX feed, the only
    feed available without a paid subscription.
    """

    def __init__(self, api_key: str, secret_key: str) -> None:
        self._client = StockHistoricalDataClient(api_key, secret_key)

    def get_historical_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> list[MarketBar]:
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=_TIMEFRAME_MAP[timeframe],
            start=start,
            end=end,
            feed=DataFeed.IEX,
        )

        bar_set = self._client.get_stock_bars(request)

        if isinstance(bar_set, dict):
            # get_stock_bars only returns a plain dict when raw_data=True
            # is passed, which we never do. This branch should be
            # unreachable in practice; it exists to narrow the type for
            # mypy and to fail loudly rather than silently if that ever
            # changes.
            raise TypeError(
                "Expected a BarSet from alpaca-py, got a raw dict. "
                "This indicates an unexpected SDK configuration."
            )

        raw_bars = bar_set.data.get(symbol, [])

        return [
            MarketBar(
                symbol=symbol,
                timestamp=bar.timestamp,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                trade_count=int(bar.trade_count) if bar.trade_count is not None else None,
                vwap=bar.vwap,
            )
            for bar in raw_bars
        ]