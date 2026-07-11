"""Integration tests for AlpacaBroker, run against the real Alpaca
paper account. Places and immediately cancels a real (unfilled) limit
order far from market price, so it never actually executes.
"""

from app.core.config import get_settings
from app.trading_engine.domain.order import Order, OrderSide, OrderStatus, OrderType
from app.trading_engine.domain.portfolio import Portfolio
from app.trading_engine.execution.alpaca_broker import AlpacaBroker


def _broker() -> AlpacaBroker:
    settings = get_settings()
    return AlpacaBroker(settings.alpaca_api_key, settings.alpaca_secret_key)


def test_get_portfolio_returns_domain_types():
    broker = _broker()
    portfolio = broker.get_portfolio()

    assert isinstance(portfolio, Portfolio)
    assert isinstance(portfolio.cash, float)
    for position in portfolio.positions.values():
        assert type(position).__name__ == "Position"


def test_place_and_cancel_limit_order_far_from_market():
    broker = _broker()

    # $1 limit buy on AAPL will never fill — safe to place and cancel.
    order = broker.place_order(
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=1,
        limit_price=1.00,
    )

    assert isinstance(order, Order)
    assert order.symbol == "AAPL"
    assert order.side == OrderSide.BUY
    assert order.order_type == OrderType.LIMIT
    assert order.status in (OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED)

    fetched = broker.get_order(str(order.id))
    assert fetched.id == order.id

    broker.cancel_order(str(order.id))

    canceled = broker.get_order(str(order.id))
    assert canceled.status in (OrderStatus.CANCELED, OrderStatus.PARTIALLY_FILLED)