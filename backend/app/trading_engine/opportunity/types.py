"""Domain types produced by the Opportunity Engine's planner.

Deliberately in-memory only, never persisted: DecisionLog, Order, and
PortfolioSnapshot already provide the durable audit trail an
evaluation cycle needs. ExecutionPlan is an intermediate planning
artifact that exists only for the duration of one cycle -- there's no
current consumer for a historical record of whole plans, only for
their outcomes (which DecisionLog.plan_outcome captures).
"""

import enum
from dataclasses import dataclass, field

from app.schemas.strategy import AssetRule
from app.trading_engine.domain.signal import Signal


@dataclass(frozen=True)
class Opportunity:
    """One BUY signal that has cleared the Rule Evaluator, not yet
    evaluated by the planner.

    signal is the real Signal evaluate_strategy produced -- carried
    through unchanged, never reconstructed later. This preserves its
    actual triggered_rules and its real bar timestamp all the way into
    execution and the DecisionLog, rather than the planner or the
    worker inventing a substitute.

    current_price and requested_capital are resolved once, at
    collection time, since both depend only on the candidate itself
    (its own rule's capital_allocation and the portfolio's total value
    at the start of the cycle) -- never on which other candidates
    exist or what order the plan ends up considering them in.
    """

    symbol: str
    rule: AssetRule
    signal: Signal
    current_price: float
    requested_capital: float


class PlanOutcome(str, enum.Enum):
    """SKIPPED_LIQUIDITY and DEFERRED both mean the planner made the
    call without the Risk Manager ever being consulted for real.
    SELECTED means the planner chose this candidate and evaluate_risk
    approved it against the *simulated* portfolio -- it is still
    re-validated against the real portfolio at actual execution time
    before an order is placed, so SELECTED is provisional, not final.
    A SELECTED entry can still end up with risk_approved=False in the
    DecisionLog if reality (the real portfolio at execution time)
    diverged from the simulation.
    """

    SKIPPED_LIQUIDITY = "skipped_liquidity"
    DEFERRED = "deferred"
    SELECTED = "selected"


@dataclass(frozen=True)
class ExecutionPlanEntry:
    opportunity: Opportunity
    outcome: PlanOutcome
    reason: str
    order_in_plan: int | None = None          # None only for SKIPPED_LIQUIDITY
    simulated_quantity: float | None = None   # set only when outcome == SELECTED; provisional


@dataclass(frozen=True)
class ExecutionPlan:
    entries: list[ExecutionPlanEntry] = field(default_factory=list)

    @property
    def selected(self) -> list[ExecutionPlanEntry]:
        """What evaluation_job actually attempts to execute. Each one
        still gets a final, real evaluate_risk call at execution time,
        exactly like every signal always has."""
        return [e for e in self.entries if e.outcome == PlanOutcome.SELECTED]