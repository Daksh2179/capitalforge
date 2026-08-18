"""Buy-and-hold benchmark simulation. Deliberately NOT part of
engine.py -- a benchmark has no buy/sell conditions to evaluate at
all, so it doesn't belong in the rule-replay engine; it's structurally
a different, much simpler computation (buy once, hold, mark to
market). engine.py and simulator.py are untouched by this file.
"""

from datetime import datetime

from app.trading_engine.domain.market_bar import MarketBar


def simulate_buy_and_hold(bars: list[MarketBar], starting_cash: float) -> list[tuple[datetime, float]]:
    """Buys as many shares as starting_cash affords at the first bar's
    close, holds for the entire window, marking to market on every
    bar. Feeds the same metrics.py functions the rule-based backtest
    uses -- both produce an equity_curve of the same shape."""
    if not bars:
        return []
    shares = starting_cash / bars[0].close
    return [(bar.timestamp, shares * bar.close) for bar in bars]