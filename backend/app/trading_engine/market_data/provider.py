"""MarketDataProvider: the interface every market data source implements.

The rest of the engine depends only on this interface, never on a
specific provider. AlpacaMarketData is the first and only implementation
in V1.
"""

from abc import ABC, abstractmethod
from datetime import datetime

from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.domain.timeframe import Timeframe


class MarketDataProvider(ABC):
    """Abstract interface for fetching historical OHLCV bars."""

    @abstractmethod
    def get_historical_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> list[MarketBar]:
        """Fetch historical bars for a symbol between start and end,
        inclusive, ordered oldest to newest. Must return MarketBar
        instances only, never a provider-specific type."""
        raise NotImplementedError