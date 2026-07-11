"""AlpacaBroker: the only file besides AlpacaMarketData permitted to
import alpaca-py. Translates Alpaca's account/position/order objects
into our own domain types immediately — nothing Alpaca-specific leaves
this module.
"""

import uuid

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide as AlpacaOrderSide
from alpaca.trading.enums import OrderStatus as AlpacaOrderStatus
from alpaca.trading.enums import OrderType as AlpacaOrderType
from alpaca.trading.enums import TimeInForce
from alpaca.trading.requests import (
    LimitOrderRequest,
    MarketOrderRequest,
    StopLimitOrderRequest,
    StopOrderRequest,
)

from app.trading_engine.domain.order import Order, OrderSide, OrderStatus, OrderType
from app.trading_engine.domain.portfolio import Portfolio
from app.trading_engine.domain.position import Position
from app.trading_engine.execution.broker import Broker

_SIDE_TO_ALPACA = {
    OrderSide.BUY: AlpacaOrderSide.BUY,
    OrderSide.SELL: AlpacaOrderSide.SELL,
}

_STATUS_FROM_ALPACA: dict[AlpacaOrderStatus, OrderStatus] = {
    AlpacaOrderStatus.NEW: OrderStatus.NEW,
    AlpacaOrderStatus.PARTIALLY_FILLED: OrderStatus.PARTIALLY_FILLED,
    AlpacaOrderStatus.FILLED: OrderStatus.FILLED,
    AlpacaOrderStatus.CANCELED: OrderStatus.CANCELED,
    AlpacaOrderStatus.REJECTED: OrderStatus.REJECTED,
}


class AlpacaBroker(Broker):
    def __init__(self, api_key: str, secret_key: str) -> None:
        self._client = TradingClient(api_key, secret_key, paper=True)

    def get_portfolio(self) -> Portfolio:
        account = self._client.get_account()
        raw_positions = self._client.get_all_positions()

        if isinstance(account, dict):
            raise TypeError(
                "Expected a TradeAccount from alpaca-py, got a raw dict. "
                "This indicates an unexpected SDK configuration."
            )
        if account.cash is None:
            raise ValueError("Alpaca account response had no cash value")

        positions: dict[str, Position] = {}
        for p in raw_positions:
            if isinstance(p, str):
                raise TypeError(
                    "Expected Position objects from alpaca-py, got a raw string. "
                    "This indicates an unexpected SDK configuration."
                )
            positions[p.symbol] = Position(
                symbol=p.symbol,
                quantity=float(p.qty),
                average_entry_price=float(p.avg_entry_price),
                current_price=float(p.current_price) if p.current_price else None,
            )

        return Portfolio(cash=float(account.cash), positions=positions)

    def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        limit_price: float | None = None,
        stop_price: float | None = None,
    ) -> Order:
        alpaca_side = _SIDE_TO_ALPACA[side]
        request = self._build_request(symbol, alpaca_side, order_type, quantity, limit_price, stop_price)

        raw_order = self._client.submit_order(order_data=request)
        return self._to_domain_order(raw_order)

    def get_order(self, order_id: str) -> Order:
        raw_order = self._client.get_order_by_id(uuid.UUID(order_id))
        return self._to_domain_order(raw_order)

    def cancel_order(self, order_id: str) -> None:
        self._client.cancel_order_by_id(uuid.UUID(order_id))

    def _build_request(
        self,
        symbol: str,
        alpaca_side: AlpacaOrderSide,
        order_type: OrderType,
        quantity: float,
        limit_price: float | None,
        stop_price: float | None,
    ):
        if order_type == OrderType.MARKET:
            return MarketOrderRequest(
                symbol=symbol, qty=quantity, side=alpaca_side, time_in_force=TimeInForce.DAY
            )
        if order_type == OrderType.LIMIT:
            if limit_price is None:
                raise ValueError("limit_price is required for LIMIT orders")
            return LimitOrderRequest(
                symbol=symbol, qty=quantity, side=alpaca_side,
                time_in_force=TimeInForce.DAY, limit_price=limit_price,
            )
        if order_type == OrderType.STOP:
            if stop_price is None:
                raise ValueError("stop_price is required for STOP orders")
            return StopOrderRequest(
                symbol=symbol, qty=quantity, side=alpaca_side,
                time_in_force=TimeInForce.DAY, stop_price=stop_price,
            )
        if order_type == OrderType.STOP_LIMIT:
            if limit_price is None or stop_price is None:
                raise ValueError("limit_price and stop_price are both required for STOP_LIMIT orders")
            return StopLimitOrderRequest(
                symbol=symbol, qty=quantity, side=alpaca_side, time_in_force=TimeInForce.DAY,
                limit_price=limit_price, stop_price=stop_price,
            )
        raise ValueError(f"Unsupported order type: {order_type}")

    def _to_domain_order(self, raw_order) -> Order:
        alpaca_type = raw_order.order_type
        if alpaca_type == AlpacaOrderType.MARKET:
            order_type = OrderType.MARKET
        elif alpaca_type == AlpacaOrderType.LIMIT:
            order_type = OrderType.LIMIT
        elif alpaca_type == AlpacaOrderType.STOP:
            order_type = OrderType.STOP
        elif alpaca_type == AlpacaOrderType.STOP_LIMIT:
            order_type = OrderType.STOP_LIMIT
        else:
            raise ValueError(f"Unsupported Alpaca order type in response: {alpaca_type}")

        return Order(
            id=raw_order.id,
            symbol=raw_order.symbol,
            side=OrderSide.BUY if raw_order.side == AlpacaOrderSide.BUY else OrderSide.SELL,
            order_type=order_type,
            quantity=float(raw_order.qty),
            status=_STATUS_FROM_ALPACA.get(raw_order.status, OrderStatus.NEW),
            submitted_at=raw_order.submitted_at,
            limit_price=float(raw_order.limit_price) if raw_order.limit_price else None,
            stop_price=float(raw_order.stop_price) if raw_order.stop_price else None,
            filled_quantity=float(raw_order.filled_qty) if raw_order.filled_qty else 0.0,
            filled_avg_price=float(raw_order.filled_avg_price) if raw_order.filled_avg_price else None,
            filled_at=raw_order.filled_at,
        )