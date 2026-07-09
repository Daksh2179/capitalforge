"""SQLAlchemy declarative base and shared mixins."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all ORM models. Every model in app/models/ inherits from this."""

    pass


class IDMixin:
    """Adds a UUID primary key column, generated in Python at insert time."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class CreatedAtMixin:
    """Adds a UTC created_at timestamp column, set once at insert and never modified."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class UpdatedAtMixin:
    """Adds a UTC updated_at timestamp column, refreshed automatically on every update."""

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )