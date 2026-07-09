"""Relative Strength Index, using Wilder's smoothing method."""

from app.trading_engine.domain.market_bar import MarketBar


def calculate_rsi(bars: list[MarketBar], period: int = 14) -> list[float | None]:
    """Return Wilder's RSI of closing prices, aligned by index to bars.

    Requires period+1 bars minimum (period price changes need period+1
    prices). The first `period` changes seed the initial average
    gain/loss as a simple average; subsequent values use Wilder's
    smoothing (equivalent to an EMA with alpha = 1/period).
    """
    closes = [bar.close for bar in bars]
    result: list[float | None] = [None] * len(closes)

    if len(closes) < period + 1:
        return result

    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(c, 0.0) for c in changes]
    losses = [max(-c, 0.0) for c in changes]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    first_rsi_index = period
    result[first_rsi_index] = _rsi_from_averages(avg_gain, avg_loss)

    for i in range(period, len(changes)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        result[i + 1] = _rsi_from_averages(avg_gain, avg_loss)

    return result


def _rsi_from_averages(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))