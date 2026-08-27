"""Order: runtime domain representation of a submitted trading order.

Shared shape used by Broker implementations (AlpacaBroker) and the
backtest simulator alike. Distinct from the ORM Order model used for
persistence — translation between the two happens at the
persistence/service boundary, not here.
"""

import enum
import uuid
from dataclasses import dataclass
from datetime import datetime


class OrderSide(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, enum.Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, enum.Enum):
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    # A day-order (every order this app submits uses TimeInForce.DAY)
    # that didn't fill by market close. Distinct from CANCELED --
    # nothing cancelled it, the trading day simply ended. Kept as its
    # own explicit state rather than collapsed into CANCELED, since
    # collapsing it would hide the real reason.
    DONE_FOR_DAY = "done_for_day"
    # Alpaca returned a status this app doesn't recognize (e.g. a
    # future addition to their API). Never silently guessed as NEW --
    # treated as non-terminal so it keeps getting re-checked, since
    # whether it will eventually resolve into a known state is itself
    # unknown.
    UNKNOWN = "unknown"


# Statuses Alpaca has said will receive no further updates. Anything
# not in this set is treated as still worth polling, including UNKNOWN.
TERMINAL_ORDER_STATUSES = frozenset({
    OrderStatus.FILLED,
    OrderStatus.CANCELED,
    OrderStatus.REJECTED,
    OrderStatus.EXPIRED,
    OrderStatus.DONE_FOR_DAY,
})


def is_terminal(status: OrderStatus) -> bool:
    return status in TERMINAL_ORDER_STATUSES


@dataclass
class Order:
    """Mutable: status and filled_* fields change as the order
    progresses through its lifecycle, unlike MarketBar/Signal, which
    represent settled historical facts.
    """

    id: uuid.UUID
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    status: OrderStatus
    submitted_at: datetime
    limit_price: float | None = None
    stop_price: float | None = None
    filled_quantity: float = 0.0
    filled_avg_price: float | None = None
    filled_at: datetime | None = None