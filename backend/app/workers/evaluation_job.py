"""Evaluation job: the orchestrator. Coordinates the pipeline for one
Portfolio Strategy, one cycle.

Sync pending orders -> Collect signals -> execute SELLs -> refresh
portfolio -> Opportunity Engine builds an Execution Plan -> execute the
plan's selected BUYs -> one portfolio snapshot for the whole cycle.

SELLs are never ranked or contested for capital (see
docs/decisions.md), so they execute immediately once collected,
freeing cash the same cycle's BUY plan can then use. Contains no
trading decisions, no indicator math, no risk logic, and no planning
logic itself -- only calls the components that do, in the right order.

Order sync: Alpaca is the source of truth for whether an order
actually executed -- CapitalForge's own Order rows are only ever a
cache of Alpaca's last-known state (see
app/trading_engine/domain/order.py's TERMINAL_ORDER_STATUSES and
app/services/trading_cycle_service.py's update_order_from_broker).
Every cycle, before anything else, this strategy's still-pending
orders (from THIS cycle or any past one -- no special-casing for old
data) get re-checked against Alpaca and corrected in place. A failed
Alpaca call for one order is logged and skipped, never guessed at,
and never blocks the rest of the cycle.

Smart pause: a PAUSED strategy still runs SELL/exit evaluation in
full (existing positions stay protected by their stop loss/take
profit/sell conditions) -- only the BUY side (Opportunity Engine
planning and execution) is suspended. This is deliberate: a strategy
that stops protecting open positions the moment it's paused would be
the opposite of what "pause" should mean to a user. Buy conditions
that would have triggered are still logged, honestly, with
plan_outcome="skipped_paused" -- never silently dropped -- so
resuming later doesn't leave a gap in what "why didn't you buy" can
answer. "skipped_paused" is deliberately NOT a PlanOutcome enum
member: that enum represents real planner outcomes, and a paused
candidate never reaches the planner at all.

MarketDataProvider -> Rule Evaluator -> [SELL: Risk Manager -> Broker]
                                      -> Opportunity Engine -> [BUY: Risk Manager -> Broker]
                                      -> Persistence
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.strategy import Strategy, StrategyState, StrategyVersion
from app.schemas.strategy import AssetRule, PortfolioRules, StrategyConfig
from app.services import trading_cycle_service
from app.trading_engine.capital_allocation import resolve_requested_capital
from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.domain.order import OrderSide, OrderType
from app.trading_engine.domain.portfolio import Portfolio
from app.trading_engine.domain.signal import Signal, SignalAction
from app.trading_engine.domain.timeframe import Timeframe
from app.trading_engine.execution.broker import Broker
from app.trading_engine.market_data.provider import MarketDataProvider
from app.trading_engine.opportunity.planner import build_execution_plan
from app.trading_engine.opportunity.types import ExecutionPlanEntry, Opportunity, PlanOutcome
from app.trading_engine.risk.risk_limits import RiskLimits
from app.trading_engine.rules.evaluator import evaluate_exit, evaluate_strategy
from app.trading_engine.risk.risk_manager import RiskDecision, evaluate_risk

logger = logging.getLogger(__name__)

# V1 constraint (see docs/decisions.md): strategies operate only on
# daily bars. This constant is the single place that assumption lives.
V1_SUPPORTED_TIMEFRAME = Timeframe.DAY
LOOKBACK_DAYS = 60


def build_risk_limits(portfolio_rules: PortfolioRules) -> RiskLimits:
    """Construct RiskLimits from a strategy's PortfolioRules, falling
    back to engine defaults for any field the user didn't specify.
    """
    defaults = RiskLimits()
    return RiskLimits(
        max_position_pct=defaults.max_position_pct,
        max_portfolio_deployment_pct=(
            (portfolio_rules.max_allocation_pct / 100)
            if portfolio_rules.max_allocation_pct is not None
            else defaults.max_portfolio_deployment_pct
        ),
        min_cash_reserve_pct=(
            (portfolio_rules.cash_reserve_pct / 100)
            if portfolio_rules.cash_reserve_pct is not None
            else defaults.min_cash_reserve_pct
        ),
        max_open_positions=portfolio_rules.max_open_positions,
        total_capital_usd=portfolio_rules.total_capital_usd,
    )


def sync_pending_orders(db: Session, broker: Broker, strategy_id) -> None:
    """Reuses the already-existing, already-tested broker.get_order()
    -- this function is the only thing that was actually missing.
    Scoped to every non-terminal Order under ANY version of this one
    strategy, so a stale order from a past version gets corrected the
    same way a brand-new one would, with no separate "historical"
    code path. Alpaca is authoritative: update_order_from_broker
    always overwrites local fields with what Alpaca currently reports,
    never the reverse. A failed Alpaca call for one order is logged
    and skipped -- that order's local state is left completely
    untouched, and the rest of this strategy's pending orders still
    get checked."""
    for order in trading_cycle_service.list_non_terminal_orders(db, strategy_id=strategy_id):
        try:
            fresh = broker.get_order(order.alpaca_order_id)
        except Exception:
            logger.warning(
                "sync_pending_orders: failed to fetch order %s from Alpaca",
                order.alpaca_order_id, exc_info=True,
            )
            continue
        trading_cycle_service.update_order_from_broker(db, order=order, fresh=fresh)


def run_evaluation_cycle(
    db: Session,
    *,
    strategy: Strategy,
    strategy_version: StrategyVersion,
    market_data: MarketDataProvider,
    broker: Broker,
) -> None:
    sync_pending_orders(db, broker, strategy.id)

    config = StrategyConfig.model_validate(strategy_version.config_json)
    risk_limits = build_risk_limits(config.portfolio_rules)

    portfolio = broker.get_portfolio()
    bars_by_symbol = _collect_bars(market_data, config.asset_rules, portfolio)

    sell_candidates, buy_candidates = _classify_signals(
        db, strategy_version_id=strategy_version.id,
        asset_rules=config.asset_rules, bars_by_symbol=bars_by_symbol, portfolio=portfolio,
    )

    _execute_sells(
        db, strategy_version_id=strategy_version.id, sell_candidates=sell_candidates,
        bars_by_symbol=bars_by_symbol, risk_limits=risk_limits, broker=broker,
    )

    if strategy.state == StrategyState.PAUSED:
        _log_paused_buy_candidates(
            db, strategy_version_id=strategy_version.id,
            buy_candidates=buy_candidates, bars_by_symbol=bars_by_symbol,
        )
    else:
        portfolio = broker.get_portfolio()  # refreshed: SELL proceeds now available
        opportunities = _build_opportunities(buy_candidates, bars_by_symbol, portfolio)
        plan = build_execution_plan(opportunities, portfolio, bars_by_symbol, risk_limits)

        _execute_plan(
            db, strategy_version_id=strategy_version.id, plan_entries=plan.entries,
            bars_by_symbol=bars_by_symbol, risk_limits=risk_limits, broker=broker,
        )

    final_portfolio = broker.get_portfolio()
    trading_cycle_service.record_portfolio_snapshot(
        db, strategy_id=strategy.id, portfolio=final_portfolio
    )


def _collect_bars(
    market_data: MarketDataProvider, asset_rules: list[AssetRule], portfolio: Portfolio
) -> dict[str, list[MarketBar]]:
    """Fetched once per cycle for the union of every asset_rule's
    symbol (needed for SELL or BUY evaluation) and every currently
    held symbol (needed for the planner's correlation calc, even if a
    held position has no asset_rule of its own -- e.g. a manually
    opened leftover position)."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=LOOKBACK_DAYS)
    symbols = {rule.symbol for rule in asset_rules} | set(portfolio.positions)
    return {
        symbol: market_data.get_historical_bars(symbol, V1_SUPPORTED_TIMEFRAME, start, end)
        for symbol in symbols
    }


def _classify_signals(
    db: Session, *, strategy_version_id, asset_rules: list[AssetRule],
    bars_by_symbol: dict[str, list[MarketBar]], portfolio: Portfolio,
) -> tuple[list[tuple[AssetRule, Signal]], list[tuple[AssetRule, Signal]]]:
    """Evaluates every asset_rule's signal without executing anything.
    HOLD and unevaluated signals are logged immediately here, since
    neither a SELL execution pass nor the planner ever needs to see
    them -- there's nothing further to decide. A rule with no bars at
    all is skipped entirely (no log row), matching prior behavior."""
    sell_candidates: list[tuple[AssetRule, Signal]] = []
    buy_candidates: list[tuple[AssetRule, Signal]] = []

    for rule in asset_rules:
        bars = bars_by_symbol.get(rule.symbol, [])
        if not bars:
            continue

        position = portfolio.positions.get(rule.symbol)
        signal = evaluate_exit(position, bars, rule) if position else evaluate_strategy(bars, rule)

        if signal.action == SignalAction.SELL:
            sell_candidates.append((rule, signal))
        elif signal.action == SignalAction.BUY:
            buy_candidates.append((rule, signal))
        else:
            trading_cycle_service.log_decision(
                db, strategy_version_id=strategy_version_id, latest_bar=bars[-1],
                signal=signal, risk_decision=None, plan_outcome=None,
            )

    return sell_candidates, buy_candidates


def _execute_sells(
    db: Session, *, strategy_version_id, sell_candidates: list[tuple[AssetRule, Signal]],
    bars_by_symbol: dict[str, list[MarketBar]], risk_limits: RiskLimits, broker: Broker,
) -> None:
    """SELLs are never ranked or contested for capital, so each one
    executes immediately, sequentially, against the real broker --
    there's no reason to wait for planning. plan_outcome is always
    None: SELLs never reach the Opportunity Engine. Deliberately runs
    the same way regardless of whether the strategy is paused --
    protecting existing positions is exactly what pause should NOT
    suspend."""
    for rule, signal in sell_candidates:
        bars = bars_by_symbol[rule.symbol]
        portfolio = broker.get_portfolio()
        risk_decision = evaluate_risk(signal, portfolio, rule, risk_limits, current_price=bars[-1].close)

        if risk_decision.approved and risk_decision.quantity:
            domain_order = broker.place_order(
                symbol=rule.symbol, side=OrderSide.SELL,
                order_type=OrderType.MARKET, quantity=risk_decision.quantity,
            )
            trading_cycle_service.record_order(
                db, strategy_version_id=strategy_version_id, domain_order=domain_order
            )

        trading_cycle_service.log_decision(
            db, strategy_version_id=strategy_version_id, latest_bar=bars[-1],
            signal=signal, risk_decision=risk_decision, plan_outcome=None,
        )


def _log_paused_buy_candidates(
    db: Session, *, strategy_version_id, buy_candidates: list[tuple[AssetRule, Signal]],
    bars_by_symbol: dict[str, list[MarketBar]],
) -> None:
    """Buy conditions still get evaluated and logged while paused --
    never silently dropped -- but never reach the Opportunity Engine
    at all. plan_outcome is the literal string "skipped_paused",
    deliberately not a PlanOutcome enum member, since that enum
    represents real planner outcomes and this candidate never reached
    the planner. risk_approved is always False for the same reason
    SKIPPED_LIQUIDITY/DEFERRED already use a synthetic RiskDecision:
    the real Risk Manager never ran either."""
    for rule, signal in buy_candidates:
        bars = bars_by_symbol[rule.symbol]
        trading_cycle_service.log_decision(
            db, strategy_version_id=strategy_version_id, latest_bar=bars[-1],
            signal=signal,
            risk_decision=RiskDecision(approved=False, reason="Strategy is paused -- new buys are suspended."),
            plan_outcome="skipped_paused",
        )


def _build_opportunities(
    buy_candidates: list[tuple[AssetRule, Signal]],
    bars_by_symbol: dict[str, list[MarketBar]],
    portfolio: Portfolio,
) -> list[Opportunity]:
    """requested_capital is resolved against the portfolio's total
    value as of right now (post-SELL, pre-plan) -- the same
    resolve_requested_capital the Risk Manager itself uses, so the
    liquidity check's estimate and the Risk Manager's real math can
    never define "requested capital" two different ways."""
    opportunities = []
    for rule, signal in buy_candidates:
        bars = bars_by_symbol[rule.symbol]
        current_price = bars[-1].close
        requested_capital = resolve_requested_capital(
            rule.capital_allocation, portfolio.total_value, current_price
        )
        opportunities.append(Opportunity(
            symbol=rule.symbol, rule=rule, signal=signal,
            current_price=current_price, requested_capital=requested_capital,
        ))
    return opportunities


def _execute_plan(
    db: Session, *, strategy_version_id, plan_entries: list[ExecutionPlanEntry],
    bars_by_symbol: dict[str, list[MarketBar]], risk_limits: RiskLimits, broker: Broker,
) -> None:
    """Walks the plan in order_in_plan order (SKIPPED_LIQUIDITY entries
    have no order_in_plan and are logged first, order among themselves
    doesn't matter). Every SELECTED entry still gets a fresh, real
    evaluate_risk call against the real broker state immediately
    before execution -- the planner's simulation only decided what to
    *attempt*, reality still gets the final say, same defensive
    pattern the engine has always used."""
    ordered = sorted(plan_entries, key=lambda e: e.order_in_plan if e.order_in_plan is not None else 0)

    for entry in ordered:
        opp = entry.opportunity
        bars = bars_by_symbol[opp.symbol]

        if entry.outcome != PlanOutcome.SELECTED:
            # entry.reason is the planner's own explanation (e.g. a
            # liquidity or capital-competition message) -- carried
            # through as a synthetic RiskDecision so it's actually
            # persisted, rather than discarded in favor of a generic
            # "not evaluated" string. plan_outcome (not whether
            # risk_decision is None) is what correctly signals this
            # never reached the real Risk Manager.
            trading_cycle_service.log_decision(
                db, strategy_version_id=strategy_version_id, latest_bar=bars[-1],
                signal=opp.signal, risk_decision=RiskDecision(approved=False, reason=entry.reason),
                plan_outcome=entry.outcome.value,
            )
            continue

        portfolio = broker.get_portfolio()
        risk_decision = evaluate_risk(opp.signal, portfolio, opp.rule, risk_limits, current_price=opp.current_price)

        if risk_decision.approved and risk_decision.quantity:
            domain_order = broker.place_order(
                symbol=opp.symbol, side=OrderSide.BUY,
                order_type=OrderType.MARKET, quantity=risk_decision.quantity,
            )
            trading_cycle_service.record_order(
                db, strategy_version_id=strategy_version_id, domain_order=domain_order
            )

        trading_cycle_service.log_decision(
            db, strategy_version_id=strategy_version_id, latest_bar=bars[-1],
            signal=opp.signal, risk_decision=risk_decision, plan_outcome=entry.outcome.value,
        )