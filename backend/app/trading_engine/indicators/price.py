"""PRICE pseudo-indicator: returns each bar's own close price, unchanged.

Exists so RuleCondition can express literal price thresholds (e.g.
"buy below $180") using the same indicator/operator machinery as every
other rule, without a separate schema branch.
"""

from app.trading_engine.domain.market_bar import MarketBar


def calculate_price(bars: list[MarketBar], period: int) -> list[float | None]:
    """period is accepted but ignored, to match the shared indicator
    function signature used by the registry. PRICE has no window and
    never returns None — every bar has a close price."""
    return [bar.close for bar in bars]