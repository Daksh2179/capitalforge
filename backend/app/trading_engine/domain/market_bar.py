"""MarketBar: our own OHLCV bar type, independent of any data provider.

Every MarketDataProvider implementation must return these, never a
provider-specific type (e.g. alpaca-py's Bar or a pandas DataFrame row).
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MarketBar:
    """A single OHLCV bar for one symbol at one point in time.

    Frozen (immutable) because a bar represents a historical fact once
    fetched; nothing downstream (indicators, rules, backtest) should ever
    need to mutate one.
    """

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: int | None = None
    vwap: float | None = None