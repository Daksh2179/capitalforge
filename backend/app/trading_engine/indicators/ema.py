"""Exponential Moving Average."""

from app.trading_engine.domain.market_bar import MarketBar


def calculate_ema(bars: list[MarketBar], period: int) -> list[float | None]:
    """Return the EMA of closing prices, aligned by index to bars.

    Seeded with a simple average of the first `period` closes (the
    standard seeding approach), then smoothed forward from there.
    Positions before the seed point are None.
    """
    closes = [bar.close for bar in bars]
    result: list[float | None] = [None] * len(closes)

    if len(closes) < period:
        return result

    multiplier = 2 / (period + 1)

    seed_index = period - 1
    seed = sum(closes[:period]) / period
    result[seed_index] = seed

    prev_ema = seed
    for i in range(seed_index + 1, len(closes)):
        ema = (closes[i] - prev_ema) * multiplier + prev_ema
        result[i] = ema
        prev_ema = ema

    return result