"""Unit tests for resolve_requested_capital."""

from app.schemas.strategy import CapitalAllocation
from app.trading_engine.capital_allocation import resolve_requested_capital


def test_percentage_of_portfolio_resolves_from_total_value():
    allocation = CapitalAllocation(type="percentage_of_portfolio", percentage=5)
    assert resolve_requested_capital(allocation, portfolio_total_value=10000.0, current_price=100.0) == 500.0


def test_fixed_capital_resolves_to_flat_amount():
    allocation = CapitalAllocation(type="fixed_capital", capital_usd=600)
    assert resolve_requested_capital(allocation, portfolio_total_value=10000.0, current_price=100.0) == 600.0


def test_share_count_resolves_from_current_price():
    allocation = CapitalAllocation(type="share_count", shares=7)
    assert resolve_requested_capital(allocation, portfolio_total_value=10000.0, current_price=100.0) == 700.0