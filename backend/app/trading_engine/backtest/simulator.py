"""Fill simulator: historical replay only. Never implements the Broker
interface — this is synchronous replay logic operating on a window of
already-known bars, not a live adapter with async order status. Lives
here, not in execution/, because it is structurally a different
responsibility: no real order lifecycle, no network calls, no polling.
"""

from dataclasses import dataclass

from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.domain.portfolio import Portfolio
from app.trading_engine.domain.position import Position


@dataclass(frozen=True)
class SimulatedFill:
    symbol: str
    quantity: float
    price: float


def apply_fill(portfolio: Portfolio, fill: SimulatedFill) -> Portfolio:
    """Return a new Portfolio reflecting a simulated buy fill at the
    given bar's close price. Backtest-only: fills happen instantly at
    the requested price, with no slippage modeling in this first pass
    — see docs/decisions.md for why this is a known, accepted
    simplification for now, not an oversight.
    """
    cost = fill.quantity * fill.price
    new_cash = portfolio.cash - cost

    existing = portfolio.positions.get(fill.symbol)
    if existing is None:
        new_quantity = fill.quantity
        new_avg_price = fill.price
    else:
        total_quantity = existing.quantity + fill.quantity
        new_avg_price = (
            (existing.quantity * existing.average_entry_price) + (fill.quantity * fill.price)
        ) / total_quantity
        new_quantity = total_quantity

    new_positions = dict(portfolio.positions)
    new_positions[fill.symbol] = Position(
        symbol=fill.symbol,
        quantity=new_quantity,
        average_entry_price=new_avg_price,
        current_price=fill.price,
    )

    return Portfolio(cash=new_cash, positions=new_positions)


def mark_to_market(portfolio: Portfolio, bar: MarketBar) -> Portfolio:
    """Return a new Portfolio with the given symbol's position
    current_price updated to this bar's close, for equity-curve
    tracking between trades."""
    existing = portfolio.positions.get(bar.symbol)
    if existing is None:
        return portfolio

    new_positions = dict(portfolio.positions)
    new_positions[bar.symbol] = Position(
        symbol=existing.symbol,
        quantity=existing.quantity,
        average_entry_price=existing.average_entry_price,
        current_price=bar.close,
    )
    return Portfolio(cash=portfolio.cash, positions=new_positions)