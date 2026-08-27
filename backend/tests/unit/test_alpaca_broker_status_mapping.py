"""Unit tests for AlpacaBroker's status-mapping logic (_to_domain_order)
in isolation -- no real Alpaca network calls. Constructs a minimal
stand-in for alpaca-py's raw order object (SimpleNamespace exposing
just the attributes _to_domain_order actually reads) since alpaca-py
gives no lighter-weight way to build one. Tests a private method
deliberately: this pure translation logic has no other seam, since the
public get_order()/place_order() both require a live network call.
"""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from alpaca.trading.enums import OrderSide as AlpacaOrderSide
from alpaca.trading.enums import OrderStatus as AlpacaOrderStatus
from alpaca.trading.enums import OrderType as AlpacaOrderType

from app.trading_engine.domain.order import OrderStatus
from app.trading_engine.execution.alpaca_broker import AlpacaBroker


def _broker() -> AlpacaBroker:
    # Dummy credentials -- TradingClient.__init__ only stores them,
    # it makes no network call at construction time.
    return AlpacaBroker("fake-key", "fake-secret")


def _raw_order(status: AlpacaOrderStatus, **overrides) -> SimpleNamespace:
    defaults = dict(
        id=uuid.uuid4(), symbol="AAPL", side=AlpacaOrderSide.BUY,
        order_type=AlpacaOrderType.MARKET, status=status,
        submitted_at=datetime.now(timezone.utc), limit_price=None, stop_price=None,
        qty="5", filled_qty="0", filled_avg_price=None, filled_at=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_expired_status_maps_correctly():
    order = _broker()._to_domain_order(_raw_order(AlpacaOrderStatus.EXPIRED))
    assert order.status == OrderStatus.EXPIRED


def test_done_for_day_status_maps_correctly():
    order = _broker()._to_domain_order(_raw_order(AlpacaOrderStatus.DONE_FOR_DAY))
    assert order.status == OrderStatus.DONE_FOR_DAY


def test_unrecognized_status_maps_to_unknown_not_new(caplog):
    # SUSPENDED is a real Alpaca status this app deliberately doesn't
    # model yet -- confirms it's never silently guessed as NEW.
    order = _broker()._to_domain_order(_raw_order(AlpacaOrderStatus.SUSPENDED))

    assert order.status == OrderStatus.UNKNOWN
    assert any("unrecognized order status" in record.message for record in caplog.records)


def test_partial_fill_fields_translate_correctly():
    order = _broker()._to_domain_order(_raw_order(
        AlpacaOrderStatus.PARTIALLY_FILLED, filled_qty="2.5", filled_avg_price="150.75",
    ))
    assert order.status == OrderStatus.PARTIALLY_FILLED
    assert order.filled_quantity == 2.5
    assert order.filled_avg_price == 150.75