"""Performance metrics computed from an equity curve. Pure functions,
no side effects, no dependency on how the equity curve was produced
(backtest replay or persisted PortfolioSnapshot history — both are
just list[tuple[datetime, float]] once extracted).
"""

import math
from datetime import datetime


def total_return_pct(equity_curve: list[tuple[datetime, float]]) -> float | None:
    """Percent return from first to last value in the curve."""
    if len(equity_curve) < 2:
        return None
    start_value = equity_curve[0][1]
    end_value = equity_curve[-1][1]
    if start_value == 0:
        return None
    return ((end_value - start_value) / start_value) * 100


def max_drawdown_pct(equity_curve: list[tuple[datetime, float]]) -> float | None:
    """Largest peak-to-trough decline, as a positive percentage
    (e.g. 15.0 means a 15% drawdown from the running peak)."""
    if len(equity_curve) < 2:
        return None

    peak = equity_curve[0][1]
    max_dd = 0.0

    for _, value in equity_curve:
        if value > peak:
            peak = value
        if peak > 0:
            drawdown = (peak - value) / peak * 100
            max_dd = max(max_dd, drawdown)

    return max_dd


def daily_returns(equity_curve: list[tuple[datetime, float]]) -> list[float]:
    """Day-over-day percent changes, used as the basis for Sharpe ratio."""
    returns = []
    for i in range(1, len(equity_curve)):
        prev_value = equity_curve[i - 1][1]
        curr_value = equity_curve[i][1]
        if prev_value == 0:
            continue
        returns.append((curr_value - prev_value) / prev_value)
    return returns


def sharpe_ratio(
    equity_curve: list[tuple[datetime, float]],
    risk_free_rate_annual: float = 0.0,
    trading_days_per_year: int = 252,
) -> float | None:
    """Annualized Sharpe ratio from daily equity-curve returns.
    Returns None when there's insufficient data or zero variance
    (division by zero would otherwise silently produce inf/nan).
    """
    returns = daily_returns(equity_curve)
    if len(returns) < 2:
        return None

    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
    std_dev = math.sqrt(variance)

    if std_dev < 1e-9:
        return None

    daily_risk_free = risk_free_rate_annual / trading_days_per_year
    return ((mean_return - daily_risk_free) / std_dev) * math.sqrt(trading_days_per_year)


def win_rate_pct(trade_pnls: list[float]) -> float | None:
    """Percent of trades with positive P&L. Takes realized P&L per
    trade directly, not the equity curve — this is the one metric that
    needs trade-level data rather than portfolio-level snapshots."""
    if not trade_pnls:
        return None
    wins = sum(1 for pnl in trade_pnls if pnl > 0)
    return (wins / len(trade_pnls)) * 100