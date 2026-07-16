"""Persistence boundary for one evaluation cycle: translates runtime
domain objects (Signal, RiskDecision, Order) into ORM rows. The worker
calls these functions; it never constructs ORM models itself.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.decision_log import DecisionLog
from app.models.order import Order as OrderModel
from app.models.portfolio_snapshot import PortfolioSnapshot
from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.domain.order import Order as DomainOrder
from app.trading_engine.domain.portfolio import Portfolio
from app.trading_engine.domain.signal import Signal
from app.trading_engine.risk.risk_manager import RiskDecision


def log_decision(
    db: Session,
    *,
    strategy_version_id: uuid.UUID,
    latest_bar: MarketBar,
    signal: Signal,
    risk_decision: RiskDecision | None,
) -> DecisionLog:
    """risk_decision is None when the signal never reached the risk
    manager at all (e.g. HOLD or unevaluated) — this function only
    records what happened, it doesn't decide when risk gets consulted."""
    log = DecisionLog(
        strategy_version_id=strategy_version_id,
        timestamp=signal.timestamp,
        market_snapshot_json={
            "symbol": latest_bar.symbol,
            "close": latest_bar.close,
            "volume": latest_bar.volume,
            "timestamp": latest_bar.timestamp.isoformat(),
        },
        rules_triggered_json=signal.triggered_rules,
        action_taken=signal.action.value,
        risk_approved=risk_decision.approved if risk_decision else False,
        risk_reason=risk_decision.reason if risk_decision else "not evaluated by risk manager",
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def record_order(db: Session, *, strategy_version_id: uuid.UUID, domain_order: DomainOrder) -> OrderModel:
    order = OrderModel(
        strategy_version_id=strategy_version_id,
        alpaca_order_id=str(domain_order.id),
        symbol=domain_order.symbol,
        side=domain_order.side,
        order_type=domain_order.order_type,
        quantity=domain_order.quantity,
        status=domain_order.status,
        limit_price=domain_order.limit_price,
        stop_price=domain_order.stop_price,
        filled_quantity=domain_order.filled_quantity,
        filled_avg_price=domain_order.filled_avg_price,
        submitted_at=domain_order.submitted_at,
        filled_at=domain_order.filled_at,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def record_portfolio_snapshot(
    db: Session, *, strategy_id: uuid.UUID, portfolio: Portfolio, timestamp: datetime | None = None
) -> PortfolioSnapshot:
    snapshot = PortfolioSnapshot(
        strategy_id=strategy_id,
        timestamp=timestamp or datetime.now(timezone.utc),
        cash_balance=portfolio.cash,
        positions_json={
            symbol: {
                "quantity": pos.quantity,
                "average_entry_price": pos.average_entry_price,
                "current_price": pos.current_price,
            }
            for symbol, pos in portfolio.positions.items()
        },
        total_value=portfolio.total_value,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot

def list_decision_logs(
    db: Session, *, strategy_version_id: uuid.UUID, limit: int = 50
) -> list[DecisionLog]:
    return (
        db.query(DecisionLog)
        .filter(DecisionLog.strategy_version_id == strategy_version_id)
        .order_by(DecisionLog.timestamp.desc())
        .limit(limit)
        .all()
    )


def list_orders(
    db: Session, *, strategy_version_id: uuid.UUID, limit: int = 50
) -> list[OrderModel]:
    return (
        db.query(OrderModel)
        .filter(OrderModel.strategy_version_id == strategy_version_id)
        .order_by(OrderModel.submitted_at.desc())
        .limit(limit)
        .all()
    )


def list_portfolio_snapshots(
    db: Session, *, strategy_id: uuid.UUID, limit: int = 100
) -> list[PortfolioSnapshot]:
    return (
        db.query(PortfolioSnapshot)
        .filter(PortfolioSnapshot.strategy_id == strategy_id)
        .order_by(PortfolioSnapshot.timestamp.desc())
        .limit(limit)
        .all()
    )