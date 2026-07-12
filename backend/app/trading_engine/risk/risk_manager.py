"""RiskManager: the last gate between a Signal and an actual order.
Takes a proposed BUY signal plus current portfolio state and either
approves it (returning a sized quantity) or rejects it with a reason.
Never overridden by anything upstream — this is unbypassable by design.
"""

from dataclasses import dataclass

from app.schemas.strategy import StrategyConfig
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
    config: StrategyConfig,
    limits: RiskLimits,
    current_price: float,
) -> RiskDecision:
    """current_price is passed explicitly (not read off the signal),
    since Signal doesn't carry price — only the rule outcome. Callers
    (the worker, backtest engine) already have the latest bar on hand.
    """
    if signal.action == SignalAction.SELL:
        if not signal.evaluated:
            return RiskDecision(approved=False, reason="signal was not evaluated (insufficient data)")
        position = portfolio.positions.get(signal.symbol)
        if position is None or position.quantity <= 0:
            return RiskDecision(approved=False, reason="no open position to sell")
        # Exits only reduce risk exposure, never increase it — no need to
        # re-check position/deployment/cash-reserve limits here. V1 exits
        # are always full closes, so quantity is the entire open position.
        return RiskDecision(approved=True, reason="exit approved", quantity=position.quantity)

    if signal.action != SignalAction.BUY:
        return RiskDecision(approved=False, reason="signal is not a BUY or SELL")

    if not signal.evaluated:
        return RiskDecision(approved=False, reason="signal was not evaluated (insufficient data)")

    total_value = portfolio.total_value
    if total_value <= 0:
        return RiskDecision(approved=False, reason="portfolio has no value to deploy")

    requested_value = total_value * (config.position_sizing.value_pct / 100)

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

    quantity = requested_value / current_price
    return RiskDecision(approved=True, reason="approved", quantity=quantity)