"""Stage 1a of the Opportunity Engine: candidate-intrinsic liquidity
feasibility -- can this position size realistically be executed
without moving the price against the user, independent of anything
else in the plan. Unlike capital/position-count/cash-reserve
feasibility (which depends on what else the plan has already
committed to), this never changes based on other candidates, so it's
checked once, up front, before any ordering happens.

Deliberately permissive when volume data is thin or missing: this is
a safety check layered on top of the user's own strategy, not a
primary gate that should block a trade merely because volume history
happens to be short.
"""

from app.trading_engine.domain.market_bar import MarketBar

LIQUIDITY_MAX_ADV_FRACTION = 0.01
_ADV_LOOKBACK_BARS = 20


def average_daily_volume(bars: list[MarketBar]) -> float | None:
    """Mean volume over the most recent _ADV_LOOKBACK_BARS bars.
    None if there isn't at least one bar."""
    if not bars:
        return None
    window = bars[-_ADV_LOOKBACK_BARS:]
    return sum(b.volume for b in window) / len(window)


def is_liquidity_feasible(
    requested_capital: float, current_price: float, bars: list[MarketBar]
) -> tuple[bool, str]:
    adv = average_daily_volume(bars)
    if adv is None or adv <= 0 or current_price <= 0:
        return True, "insufficient volume history to evaluate liquidity"

    max_shares = adv * LIQUIDITY_MAX_ADV_FRACTION
    max_capital = max_shares * current_price
    if requested_capital > max_capital:
        return False, (
            f"requested position (${requested_capital:.2f}) exceeds "
            f"{LIQUIDITY_MAX_ADV_FRACTION * 100:.0f}% of average daily volume "
            f"(${max_capital:.2f} at current price)"
        )
    return True, "within liquidity limits"