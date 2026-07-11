"""Position: a live holding in one symbol. Mutable — current_price is
updated every evaluation cycle by whichever component tracks market
state (AlpacaBroker for live, the backtest simulator for replay).
"""

from dataclasses import dataclass


@dataclass
class Position:
    symbol: str
    quantity: float
    average_entry_price: float
    current_price: float | None = None

    @property
    def market_value(self) -> float | None:
        if self.current_price is None:
            return None
        return self.quantity * self.current_price

    @property
    def unrealized_pl(self) -> float | None:
        if self.current_price is None:
            return None
        return (self.current_price - self.average_entry_price) * self.quantity