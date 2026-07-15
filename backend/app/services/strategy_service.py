"""Business logic for creating and versioning strategies."""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.strategy import Strategy, StrategyState, StrategyVersion, StrategyVersionSource


def create_strategy(
    db: Session,
    *,
    user_id: uuid.UUID,
    config_json: dict,
    source: StrategyVersionSource,
    confirmed_now: bool = False,
) -> Strategy:
    """Create a new Strategy along with its first StrategyVersion (version 1).

    Both rows are created in the same transaction and current_version_id is
    set before commit, so a Strategy is never left pointing at a version
    that doesn't exist.

    confirmed_now=True stamps StrategyVersion.confirmed_at with the current
    time, for the one real confirmation moment (Group 6's /agent/confirm
    endpoint). Manual API creation (Milestone 1's POST /strategies) leaves
    it None, since that path was never wired to a real confirmation step.
    """
    strategy = Strategy(user_id=user_id, state=StrategyState.DRAFT)
    db.add(strategy)
    db.flush()  # assigns strategy.id without committing, needed for the FK below

    version = StrategyVersion(
        strategy_id=strategy.id,
        version_number=1,
        config_json=config_json,
        source=source,
        confirmed_at=datetime.now(timezone.utc) if confirmed_now else None,
    )
    db.add(version)
    db.flush()  # assigns version.id, needed to set current_version_id below

    strategy.current_version_id = version.id

    db.commit()
    db.refresh(strategy)
    return strategy


def create_new_version(
    db: Session,
    *,
    strategy: Strategy,
    config_json: dict,
    source: StrategyVersionSource,
    confirmed_now: bool = False,
) -> StrategyVersion:
    """Create a new StrategyVersion for an existing strategy and repoint
    current_version_id to it. The previous StrategyVersion row is never
    modified, only superseded.
    """
    next_version_number = _get_next_version_number(db, strategy_id=strategy.id)

    version = StrategyVersion(
        strategy_id=strategy.id,
        version_number=next_version_number,
        config_json=config_json,
        source=source,
        confirmed_at=datetime.now(timezone.utc) if confirmed_now else None,
    )
    db.add(version)
    db.flush()

    strategy.current_version_id = version.id

    db.commit()
    db.refresh(version)
    return version


def get_strategy(db: Session, *, strategy_id: uuid.UUID) -> Strategy | None:
    """Fetch a strategy by id, or None if it doesn't exist."""
    return db.get(Strategy, strategy_id)


def _get_next_version_number(db: Session, *, strategy_id: uuid.UUID) -> int:
    """Compute the next version_number for a strategy, based on the highest
    existing version_number for that strategy. Not a simple count(), so a
    version created then never deleted still produces correct numbering
    even if versions were ever removed (they currently never are, but this
    is the correct way to compute it regardless).
    """
    max_version = (
        db.query(StrategyVersion.version_number)
        .filter(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.version_number.desc())
        .first()
    )
    return (max_version[0] + 1) if max_version else 1