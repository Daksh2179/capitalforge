"""PortfolioHolding ORM model — a user's staged asset, not a real
Alpaca position. No quantity or configuration status stored here;
those are deferred (quantity) or derived at read time (AI-configured
status, computed against the active Strategy's asset_rules)."""

import uuid

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IDMixin


class PortfolioHolding(Base, IDMixin, CreatedAtMixin):
    __tablename__ = "portfolio_holdings"

    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    symbol: Mapped[str] = mapped_column(String(10))