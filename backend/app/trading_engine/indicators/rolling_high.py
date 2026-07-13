"""Rolling High: the maximum `high` price over a trailing window."""

from app.trading_engine.domain.market_bar import MarketBar


def calculate_rolling_high(bars: list[MarketBar], period: int) -> list[float | None]:
    highs = [bar.high for bar in bars]
    result: list[float | None] = []

    for i in range(len(highs)):
        if i < period - 1:
            result.append(None)
            continue
        window = highs[i - period + 1 : i + 1]
        result.append(max(window))

    return result