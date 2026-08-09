"""DecisionLog: the audit trail for every evaluation cycle — what was
seen, what fired, whether risk approved it, what action was taken.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IDMixin


class DecisionLog(Base, IDMixin, CreatedAtMixin):
    __tablename__ = "decision_logs"

    strategy_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategy_versions.id"), nullable=False
    )

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    market_snapshot_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    rules_triggered_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    action_taken: Mapped[str] = mapped_column(String, nullable=False)
    risk_approved: Mapped[bool] = mapped_column(nullable=False)
    risk_reason: Mapped[str] = mapped_column(String, nullable=False)

    # Null for every SELL and every HOLD/unevaluated row -- neither
    # ever reaches the Opportunity Engine's planner. For a BUY row,
    # one of PlanOutcome's values ("skipped_liquidity", "deferred",
    # "selected"). Deliberately independent of risk_approved: a
    # "selected" row can still have risk_approved=False if the real
    # portfolio at execution time diverged from the planner's
    # simulation. See app/trading_engine/opportunity/types.py.
    plan_outcome: Mapped[str | None] = mapped_column(String, nullable=True)

    # Filled in asynchronously by the agent module later; decision
    # logging must never block on an LLM call.
    explanation_text: Mapped[str | None] = mapped_column(String, nullable=True)