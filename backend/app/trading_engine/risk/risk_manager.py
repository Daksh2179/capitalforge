"""RiskManager: the last gate between a Signal and an actual order.
Takes a proposed BUY or SELL signal plus current portfolio state and
either approves it (returning a sized quantity) or rejects it with a
reason. Never overridden by anything upstream — unbypassable by design.
"""

from dataclasses import dataclass

from app.schemas.strategy import AssetRule
from app.trading_engine.domain.portfolio import Portfolio
from app.trading_engine.domain.signal import Signal, SignalAction
from app.trading_engine.risk.risk_limits import RiskLimits


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: str
    quantity: float | None = None


def evaluate_risk(
    signal: Signal,
    portfolio: Portfolio,
    rule: AssetRule,
    limits: RiskLimits,
    current_price: float,
) -> RiskDecision:
    """current_price is passed explicitly (not read off the signal),
    since Signal doesn't carry price — only the rule outcome.
    """
    if signal.action == SignalAction.SELL:
        if not signal.evaluated:
            return RiskDecision(approved=False, reason="signal was not evaluated (insufficient data)")
        position = portfolio.positions.get(signal.symbol)
        if position is None or position.quantity <= 0:
            return RiskDecision(approved=False, reason="no open position to sell")
        return RiskDecision(approved=True, reason="exit approved", quantity=position.quantity)

    if signal.action != SignalAction.BUY:
        return RiskDecision(approved=False, reason="signal is not a BUY or SELL")

    if not signal.evaluated:
        return RiskDecision(approved=False, reason="signal was not evaluated (insufficient data)")

    total_value = portfolio.total_value
    if total_value <= 0:
        return RiskDecision(approved=False, reason="portfolio has no value to deploy")

    if limits.max_open_positions is not None:
        already_holds_this_symbol = signal.symbol in portfolio.positions
        open_count = len(portfolio.positions)
        if not already_holds_this_symbol and open_count >= limits.max_open_positions:
            return RiskDecision(
                approved=False,
                reason=(
                    f"opening {signal.symbol} would exceed max_open_positions "
                    f"limit of {limits.max_open_positions} (currently {open_count} open)"
                ),
            )

    allocation = rule.capital_allocation
    if allocation.type == "percentage_of_portfolio":
        assert allocation.percentage is not None
        requested_value = total_value * (allocation.percentage / 100)
    elif allocation.type == "fixed_capital":
        assert allocation.capital_usd is not None
        requested_value = allocation.capital_usd
    else:  # share_count
        assert allocation.shares is not None
        requested_value = allocation.shares * current_price

    existing_position = portfolio.positions.get(signal.symbol)
    existing_value = existing_position.market_value or 0.0 if existing_position else 0.0

    projected_position_value = existing_value + requested_value
    max_position_value = total_value * limits.max_position_pct
    if projected_position_value > max_position_value:
        return RiskDecision(
            approved=False,
            reason=(
                f"position size would reach {projected_position_value:.2f}, "
                f"exceeding max_position_pct limit of {max_position_value:.2f}"
            ),
        )

    projected_deployed_value = portfolio.positions_value + requested_value
    max_deployed_value = total_value * limits.max_portfolio_deployment_pct
    if projected_deployed_value > max_deployed_value:
        return RiskDecision(
            approved=False,
            reason=(
                f"total deployment would reach {projected_deployed_value:.2f}, "
                f"exceeding max_portfolio_deployment_pct limit of {max_deployed_value:.2f}"
            ),
        )

    remaining_cash_after = portfolio.cash - requested_value
    min_cash_required = total_value * limits.min_cash_reserve_pct
    if remaining_cash_after < min_cash_required:
        return RiskDecision(
            approved=False,
            reason=(
                f"remaining cash {remaining_cash_after:.2f} would fall below "
                f"min_cash_reserve_pct floor of {min_cash_required:.2f}"
            ),
        )

    if limits.total_capital_usd is not None:
        currently_deployed = portfolio.positions_value
        projected_deployed = currently_deployed + requested_value
        if projected_deployed > limits.total_capital_usd:
            return RiskDecision(
                approved=False,
                reason=(
                    f"would exceed total_capital_usd limit of {limits.total_capital_usd:.2f} "
                    f"(currently deployed: {currently_deployed:.2f})"
                ),
            )

    quantity = requested_value / current_price
    return RiskDecision(approved=True, reason="approved", quantity=quantity)