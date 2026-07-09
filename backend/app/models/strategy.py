"""Strategy and StrategyVersion ORM models."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, IDMixin, UpdatedAtMixin


class StrategyState(str, enum.Enum):
    """Lifecycle states for a Strategy. The agent layer may only act while in DRAFT."""

    DRAFT = "draft"
    VALIDATED = "validated"
    BACKTESTED = "backtested"
    CONFIRMED = "confirmed"
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"


class StrategyVersionSource(str, enum.Enum):
    """Where a given StrategyVersion's config originated from."""

    MANUAL = "manual"
    CHAT = "chat"


class Strategy(Base, IDMixin, CreatedAtMixin, UpdatedAtMixin):
    """A user's durable strategy identity. Tracks lifecycle state and which
    version is currently in effect. Mutable: state and current_version_id
    change over the strategy's life, unlike StrategyVersion which is immutable.
    """

    __tablename__ = "strategies"

    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)

    state: Mapped[StrategyState] = mapped_column(
        Enum(StrategyState, name="strategy_state"),
        nullable=False,
        default=StrategyState.DRAFT,
    )

    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategy_versions.id", use_alter=True, name="fk_current_version"),
        nullable=True,
    )

    versions: Mapped[list["StrategyVersion"]] = relationship(
        back_populates="strategy",
        foreign_keys="StrategyVersion.strategy_id",
        cascade="all, delete-orphan",
    )

    current_version: Mapped["StrategyVersion | None"] = relationship(
        foreign_keys=[current_version_id],
        post_update=True,
    )


class StrategyVersion(Base, IDMixin, CreatedAtMixin):
    """An immutable snapshot of a strategy's configuration. Every trade, order,
    and decision log references a specific version, so historical records
    remain accurate even after a strategy is edited. Deliberately has no
    updated_at column: its absence signals that rows here are never modified
    after creation, only superseded by a new row.
    """

    __tablename__ = "strategy_versions"
    __table_args__ = (
        UniqueConstraint("strategy_id", "version_number", name="uq_strategy_version_number"),
    )

    strategy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategies.id"), nullable=False
    )

    version_number: Mapped[int] = mapped_column(Integer, nullable=False)

    config_json: Mapped[dict] = mapped_column(JSONB, nullable=False)

    source: Mapped[StrategyVersionSource] = mapped_column(
        Enum(StrategyVersionSource, name="strategy_version_source"),
        nullable=False,
    )

    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    strategy: Mapped["Strategy"] = relationship(
        back_populates="versions",
        foreign_keys=[strategy_id],
    )