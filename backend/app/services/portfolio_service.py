"""Business logic for staging and reading a user's Portfolio holdings."""

import uuid

from sqlalchemy.orm import Session

from app.models.portfolio_holding import PortfolioHolding
from app.models.strategy import Strategy


def add_holding(db: Session, *, user_id: uuid.UUID, symbol: str) -> PortfolioHolding:
    """Adds a holding if not already present (idempotent — adding an
    already-staged symbol just returns the existing row, not a
    duplicate)."""
    existing = (
        db.query(PortfolioHolding)
        .filter(PortfolioHolding.user_id == user_id, PortfolioHolding.symbol == symbol)
        .first()
    )
    if existing is not None:
        return existing

    holding = PortfolioHolding(user_id=user_id, symbol=symbol)
    db.add(holding)
    db.commit()
    db.refresh(holding)
    return holding


def remove_holding(db: Session, *, user_id: uuid.UUID, symbol: str) -> bool:
    """Returns True if a holding was removed, False if none existed."""
    existing = (
        db.query(PortfolioHolding)
        .filter(PortfolioHolding.user_id == user_id, PortfolioHolding.symbol == symbol)
        .first()
    )
    if existing is None:
        return False
    db.delete(existing)
    db.commit()
    return True


def list_holdings(db: Session, *, user_id: uuid.UUID) -> list[PortfolioHolding]:
    return (
        db.query(PortfolioHolding)
        .filter(PortfolioHolding.user_id == user_id)
        .order_by(PortfolioHolding.created_at.desc())
        .all()
    )


def is_symbol_ai_configured(db: Session, *, user_id: uuid.UUID, symbol: str) -> bool:
    """Answers 'has this holding been configured for AI management,'
    not 'is the AI currently executing trades for it.' Any non-draft
    Strategy state (confirmed, active, paused) represents completed
    configuration — execution state (active vs. paused) is a separate
    concern, not mixed into this per-holding check.
    """
    strategy = (
        db.query(Strategy)
        .filter(Strategy.user_id == user_id, Strategy.state != "draft")
        .first()
    )
    if strategy is None or strategy.current_version_id is None:
        return False

    version = strategy.current_version
    if version is None:
        return False

    asset_rules = version.config_json.get("asset_rules", [])
    return any(rule.get("symbol") == symbol for rule in asset_rules)