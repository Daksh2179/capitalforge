"""Simple Moving Average."""

from app.trading_engine.domain.market_bar import MarketBar


def calculate_sma(bars: list[MarketBar], period: int) -> list[float | None]:
    """Return the SMA of closing prices, aligned by index to bars.

    Position i is None until enough history exists (i.e. until at least
    `period` bars have been seen, positions 0 to period-2 are None).
    """
    closes = [bar.close for bar in bars]
    result: list[float | None] = []

    for i in range(len(closes)):
        if i < period - 1:
            result.append(None)
            continue
        window = closes[i - period + 1 : i + 1]
        result.append(sum(window) / period)

    return result