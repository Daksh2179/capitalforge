"""MarketContext: current price and 52-week high/low for one symbol,
used to give the AI real numbers to quote back when a user's language
is subjective ("buy when it's cheap") rather than a concrete value.

Computed directly from MarketDataProvider bars, not via the indicator
registry — this is display context for conversation, not a tradable
rule primitive.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.trading_engine.domain.timeframe import Timeframe
from app.trading_engine.market_data.provider import MarketDataProvider


@dataclass(frozen=True)
class MarketContext:
    symbol: str
    current_price: float
    week_52_high: float
    week_52_low: float


def get_market_context(symbol: str, market_data: MarketDataProvider) -> MarketContext | None:
    """Returns None if there isn't enough recent data to report
    anything meaningful — callers should handle this by asking the
    user directly rather than presenting fabricated numbers."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=365)

    bars = market_data.get_historical_bars(symbol, Timeframe.DAY, start, end)
    if not bars:
        return None

    return MarketContext(
        symbol=symbol,
        current_price=bars[-1].close,
        week_52_high=max(bar.high for bar in bars),
        week_52_low=min(bar.low for bar in bars),
    )