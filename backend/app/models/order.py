"""Order: ORM persistence model for submitted trading orders.

Distinct from trading_engine.domain.order.Order (the runtime type used
by Broker implementations and the backtest simulator). Translation
between the two happens at the persistence boundary
(services/trading_cycle_service.py), never inside the engine or the
worker itself.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IDMixin
from app.trading_engine.domain.order import OrderSide, OrderStatus, OrderType


class Order(Base, IDMixin, CreatedAtMixin):
    __tablename__ = "orders"

    strategy_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategy_versions.id"), nullable=False
    )

    alpaca_order_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)

    symbol: Mapped[str] = mapped_column(String, nullable=False)
    side: Mapped[OrderSide] = mapped_column(Enum(OrderSide, name="order_side"), nullable=False)
    order_type: Mapped[OrderType] = mapped_column(Enum(OrderType, name="order_type"), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus, name="order_status"), nullable=False)

    limit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    filled_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    filled_avg_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)