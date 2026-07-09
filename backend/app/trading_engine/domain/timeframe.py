"""Our own timeframe vocabulary for market data requests.

This is deliberately separate from alpaca-py's TimeFrame/TimeFrameUnit
classes. MarketDataProvider implementations translate Timeframe into
whatever their underlying SDK expects internally; no caller of
MarketDataProvider should ever need to know or care that Alpaca exists.
"""

from enum import Enum


class Timeframe(str, Enum):
    """Supported bar intervals. Extend as new intervals are actually needed
    by a real caller, not speculatively."""

    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"