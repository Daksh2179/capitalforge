"""RiskLimits: hard-coded, engine-wide risk boundaries. Distinct from
StrategyConfig.position_sizing / exit, which are per-strategy user
preferences. These are the system's non-negotiable floor, applied on
top of whatever the strategy config requests.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskLimits:
    """All percentages are fractions of total portfolio value (e.g.
    0.25 = 25%), not of available cash, so they account for existing
    open positions correctly.
    """

    max_position_pct: float = 0.20
    max_portfolio_deployment_pct: float = 0.80
    min_cash_reserve_pct: float = 0.10