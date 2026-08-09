"""The Opportunity Engine's planner: takes one cycle's collected BUY
opportunities and the portfolio's current state, and produces a
deterministic ExecutionPlan.

Four separate passes, deliberately kept as separate functions rather
than folded into one loop, because they answer genuinely different
questions:

  1. Liquidity feasibility (candidate-intrinsic, order-independent --
     runs once, up front)
  2. Portfolio-impact evaluation (depends on the *evolving* simulated
     portfolio, recomputed after each commitment)
  3. Selection (choosing which ranked candidate to consider next)
  4. Feasibility validation (capital/position-count/cash-reserve,
     delegated to the existing, unchanged evaluate_risk -- run here
     against a simulated portfolio, and again against the real
     portfolio at actual execution time)

Nothing here invents a market thesis: liquidity is an executability
fact, portfolio impact is a backward-looking risk-structure fact, and
feasibility is the same stateless check used everywhere else in the
engine. See docs/decisions.md for the reasoning that ruled out
indicator-magnitude-based ranking.
"""

import copy

from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.domain.portfolio import Portfolio
from app.trading_engine.domain.position import Position
from app.trading_engine.opportunity.feasibility import is_liquidity_feasible
from app.trading_engine.opportunity.portfolio_impact import portfolio_impact_score
from app.trading_engine.opportunity.types import (
    ExecutionPlan,
    ExecutionPlanEntry,
    Opportunity,
    PlanOutcome,
)
from app.trading_engine.risk.risk_limits import RiskLimits
from app.trading_engine.risk.risk_manager import evaluate_risk


def _eliminate_infeasible_by_liquidity(
    opportunities: list[Opportunity], bars_by_symbol: dict[str, list[MarketBar]]
) -> tuple[list[Opportunity], list[ExecutionPlanEntry]]:
    """Stage 1a. Order-independent, so it runs exactly once, before
    any ranking or simulation begins."""
    remaining: list[Opportunity] = []
    eliminated: list[ExecutionPlanEntry] = []

    for opp in opportunities:
        bars = bars_by_symbol.get(opp.symbol, [])
        feasible, reason = is_liquidity_feasible(opp.requested_capital, opp.current_price, bars)
        if feasible:
            remaining.append(opp)
        else:
            eliminated.append(ExecutionPlanEntry(
                opportunity=opp, outcome=PlanOutcome.SKIPPED_LIQUIDITY, reason=reason,
            ))

    return remaining, eliminated


def _select_next(
    remaining: list[Opportunity],
    simulated_portfolio: Portfolio,
    bars_by_symbol: dict[str, list[MarketBar]],
) -> Opportunity:
    """Stages 2 + 3 combined: score every still-open candidate against
    the *current* simulated portfolio, then pick the single best one
    to consider next. Lower impact score (weaker or negative
    correlation with existing holdings) is preferred -- diversifying
    the portfolio over concentrating it. Candidates with no computable
    correlation rank after every candidate that has real evidence;
    among themselves, and to break exact ties, fall back to FIFO by
    AssetRule.created_at, then id -- both immutable regardless of list
    position (see docs/decisions.md on why list position isn't a
    valid ordering key).
    """

    def sort_key(opp: Opportunity) -> tuple:
        bars = bars_by_symbol.get(opp.symbol, [])
        score = portfolio_impact_score(opp.symbol, bars, simulated_portfolio, bars_by_symbol)
        has_score = score is not None
        return (
            0 if has_score else 1,
            score if has_score else 0.0,
            opp.rule.created_at,
            opp.rule.id,
        )

    return min(remaining, key=sort_key)


def _validate_and_commit(
    opp: Opportunity,
    simulated_portfolio: Portfolio,
    risk_limits: RiskLimits,
) -> tuple[PlanOutcome, str, float | None]:
    """Stage 4. Deliberately reuses evaluate_risk rather than
    reimplementing capital/position-count/cash-reserve checks --
    the Risk Manager stays the single source of truth for those rules;
    the planner only decides *when* to consult it and against what
    simulated state. opp.signal is the real Signal the Rule Evaluator
    produced -- never reconstructed here."""
    decision = evaluate_risk(opp.signal, simulated_portfolio, opp.rule, risk_limits, opp.current_price)

    if not decision.approved:
        return PlanOutcome.DEFERRED, decision.reason, None
    return PlanOutcome.SELECTED, decision.reason, decision.quantity


def _commit_to_simulation(opp: Opportunity, quantity: float, simulated_portfolio: Portfolio) -> None:
    """Mutates the planner's own simulated copy only -- never the real
    portfolio. Deducts the amount actually approved by evaluate_risk
    (quantity * current_price), NOT opp.requested_capital -- those can
    diverge for percentage_of_portfolio allocations, since the real
    approved amount depends on total_value at the moment evaluate_risk
    ran, which shifts as earlier candidates get committed within this
    same simulation. requested_capital is only ever valid for the
    Stage 1a liquidity check, computed once against the real starting
    portfolio; it is never a source of truth for cash bookkeeping.

    average_entry_price here is an approximation (it doesn't correctly
    blend with a pre-existing position at a different price) because
    this simulation is discarded the moment planning ends; it only
    needs to be accurate enough for *this cycle's* remaining
    feasibility checks, never persisted or acted on directly.
    """
    committed_capital = quantity * opp.current_price

    existing = simulated_portfolio.positions.get(opp.symbol)
    new_quantity = (existing.quantity if existing else 0.0) + quantity
    simulated_portfolio.positions[opp.symbol] = Position(
        symbol=opp.symbol, quantity=new_quantity,
        average_entry_price=opp.current_price, current_price=opp.current_price,
    )
    simulated_portfolio.cash -= committed_capital


def build_execution_plan(
    opportunities: list[Opportunity],
    portfolio: Portfolio,
    bars_by_symbol: dict[str, list[MarketBar]],
    risk_limits: RiskLimits,
) -> ExecutionPlan:
    """The planner's entry point. `portfolio` is never mutated --
    planning works entirely against an internal deep copy, so the
    caller's real Portfolio (typically straight from the broker) stays
    untouched until actual execution happens afterward."""
    remaining, entries = _eliminate_infeasible_by_liquidity(opportunities, bars_by_symbol)

    simulated = copy.deepcopy(portfolio)
    order_in_plan = 0

    while remaining:
        chosen = _select_next(remaining, simulated, bars_by_symbol)
        remaining.remove(chosen)
        order_in_plan += 1

        outcome, reason, quantity = _validate_and_commit(chosen, simulated, risk_limits)
        entries.append(ExecutionPlanEntry(
            opportunity=chosen, outcome=outcome, reason=reason,
            order_in_plan=order_in_plan, simulated_quantity=quantity,
        ))

        if outcome == PlanOutcome.SELECTED:
            assert quantity is not None
            _commit_to_simulation(chosen, quantity, simulated)

    return ExecutionPlan(entries=entries)