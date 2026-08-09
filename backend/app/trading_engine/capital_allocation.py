"""Shared resolution of an AssetRule's CapitalAllocation into a
concrete requested dollar amount. Used by both the Risk Manager (the
final, unbypassable per-trade gate) and the Opportunity Engine's
planner (pre-execution simulation) -- one implementation, so the two
can never drift apart on what a given allocation actually means in
dollars.
"""

from app.schemas.strategy import CapitalAllocation


def resolve_requested_capital(
    allocation: CapitalAllocation, portfolio_total_value: float, current_price: float
) -> float:
    if allocation.type == "percentage_of_portfolio":
        assert allocation.percentage is not None
        return portfolio_total_value * (allocation.percentage / 100)
    if allocation.type == "fixed_capital":
        assert allocation.capital_usd is not None
        return allocation.capital_usd
    # share_count
    assert allocation.shares is not None
    return allocation.shares * current_price