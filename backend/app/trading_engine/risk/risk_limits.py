"""RiskLimits: hard-coded, engine-wide risk boundaries, overridable
per-strategy via PortfolioRules (see workers/evaluation_job.py for the
construction logic). Distinct from AssetRule.capital_allocation / exit,
which are per-asset user preferences.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskLimits:
    max_position_pct: float = 0.20
    max_portfolio_deployment_pct: float = 0.80
    min_cash_reserve_pct: float = 0.10
    max_open_positions: int | None = None
    total_capital_usd: float | None = None