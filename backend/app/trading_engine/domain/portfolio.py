"""Portfolio: cash plus all open positions, for one strategy or account
context. Mutable, tracked live by the broker adapter or backtest engine.
"""

from dataclasses import dataclass, field

from app.trading_engine.domain.position import Position


@dataclass
class Portfolio:
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)

    @property
    def positions_value(self) -> float:
        return sum(p.market_value or 0.0 for p in self.positions.values())

    @property
    def total_value(self) -> float:
        return self.cash + self.positions_value