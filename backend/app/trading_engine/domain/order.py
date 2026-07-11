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