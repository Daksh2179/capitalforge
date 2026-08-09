"""IndicatorContext: computes named technical indicators for one
symbol via the SAME registry the Rule Evaluator uses -- never a
second, parallel implementation. Conversational context only, exactly
like MarketContext -- not a tradable rule primitive.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.trading_engine.domain.timeframe import Timeframe
from app.trading_engine.indicators.registry import resolve_indicator
from app.trading_engine.market_data.provider import MarketDataProvider

_LOOKBACK_DAYS = 400  # enough history for a 200-period SMA plus buffer


@dataclass(frozen=True)
class IndicatorReading:
    indicator: str
    period: int
    value: float
    # Reserved for future indicators with structured, multi-part
    # outputs (MACD line/signal/histogram, Bollinger upper/middle/lower,
    # etc.) -- deliberately unused by every current indicator and by
    # TechnicalAnalystAgent, which only ever reads `value`. Present now
    # so adding such an indicator later doesn't require redesigning
    # this type.
    components: dict[str, float] | None = None


def get_indicator_readings(
    symbol: str, market_data: MarketDataProvider, requests: list[tuple[str, int]]
) -> list[IndicatorReading]:
    """requests is a list of (indicator_name, period) pairs, e.g.
    [("RSI", 14), ("SMA", 50)]. Skips (never errors on) any pair with
    insufficient bar history or an unknown indicator name -- callers
    must treat a shorter-than-requested result list as partial, not a
    failure.
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=_LOOKBACK_DAYS)
    bars = market_data.get_historical_bars(symbol, Timeframe.DAY, start, end)
    if not bars:
        return []

    readings = []
    for indicator_name, period in requests:
        try:
            func = resolve_indicator(indicator_name)
        except ValueError:
            continue
        values = func(bars, period)
        if not values or values[-1] is None:
            continue
        readings.append(IndicatorReading(indicator=indicator_name, period=period, value=values[-1]))
    return readings