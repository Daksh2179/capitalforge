"""PortfolioSnapshot: point-in-time equity curve data. Keyed to
Strategy, not StrategyVersion — portfolio value persists across
version edits, the money doesn't reset when a strategy is modified.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IDMixin


class PortfolioSnapshot(Base, IDMixin, CreatedAtMixin):
    __tablename__ = "portfolio_snapshots"

    strategy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("strategies.id"), nullable=False)

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cash_balance: Mapped[float] = mapped_column(Float, nullable=False)
    positions_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    total_value: Mapped[float] = mapped_column(Float, nullable=False)