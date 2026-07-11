"""Broker: the interface every execution adapter implements. AlpacaBroker
is the sole V1 implementation. Never implemented by the backtest
simulator — historical replay is a fundamentally different
responsibility and lives only in trading_engine/backtest/.
"""

from abc import ABC, abstractmethod

from app.trading_engine.domain.order import Order, OrderSide, OrderType
from app.trading_engine.domain.portfolio import Portfolio


class Broker(ABC):
    @abstractmethod
    def get_portfolio(self) -> Portfolio:
        """Return current cash and open positions."""
        raise NotImplementedError

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        limit_price: float | None = None,
        stop_price: float | None = None,
    ) -> Order:
        """Submit an order and return it in whatever state the broker
        reports immediately (typically NEW), not necessarily FILLED."""
        raise NotImplementedError

    @abstractmethod
    def get_order(self, order_id: str) -> Order:
        """Fetch the current state of a previously submitted order."""
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, order_id: str) -> None:
        raise NotImplementedError