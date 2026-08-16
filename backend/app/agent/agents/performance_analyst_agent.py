"""PerformanceAnalystAgent: reads the FULL PortfolioSnapshot history
(not just the latest one) to report return and drawdown over time.
Deliberately distinct from PortfolioAnalystAgent's "how's this
strategy doing," which reports current state from a single snapshot --
this Agent's entire reason to exist is the series, not a point.

Confirmed real gap, not worked around: Order has no linkage between a
BUY and the SELL that eventually closes it -- there's no round-trip
"trade" concept in the schema at all. Win rate and per-trade P&L are
genuinely unanswerable today; this Agent says so rather than
approximating.

Total return and max drawdown are both real, deterministic,
backward-looking calculations over already-persisted total_value --
never a prediction, never invented.
"""


from sqlalchemy.orm import Session

from app.agent.agent_contracts import AgentName, CapabilityResult
from app.agent.pipeline.types import AgentExecutionContext
from app.models.portfolio_snapshot import PortfolioSnapshot
from app.services import strategy_service, trading_cycle_service

_MAX_HISTORY = 100


def _total_return_pct(snapshots_oldest_first: list[PortfolioSnapshot]) -> float | None:
    if len(snapshots_oldest_first) < 2:
        return None
    start = snapshots_oldest_first[0].total_value
    if start <= 0:
        return None
    end = snapshots_oldest_first[-1].total_value
    return (end - start) / start * 100


def _max_drawdown_pct(snapshots_oldest_first: list[PortfolioSnapshot]) -> float | None:
    if len(snapshots_oldest_first) < 2:
        return None
    peak = snapshots_oldest_first[0].total_value
    max_dd = 0.0
    for snapshot in snapshots_oldest_first:
        peak = max(peak, snapshot.total_value)
        if peak > 0:
            max_dd = max(max_dd, (peak - snapshot.total_value) / peak * 100)
    return max_dd


class PerformanceAnalystAgent:
    name = AgentName.PERFORMANCE_ANALYST

    def __init__(self, db: Session) -> None:
        self._db = db

    def execute(self, context: AgentExecutionContext) -> list[CapabilityResult]:
        grounded = context.grounded_context

        if context.strategy_id is None:
            return [CapabilityResult(
                agent=self.name, description="No active strategy to report performance for",
                facts=["I don't have an active strategy to look at right now."],
            )]

        strategy = strategy_service.get_strategy(self._db, strategy_id=context.strategy_id)
        if strategy is None:
            return [CapabilityResult(
                agent=self.name, description="No strategy found",
                facts=["I don't have a strategy to look at right now."],
            )]

        newest_first = trading_cycle_service.list_portfolio_snapshots(
            self._db, strategy_id=context.strategy_id, limit=_MAX_HISTORY
        )
        oldest_first = list(reversed(newest_first))

        if grounded.resolved_entities:
            return [self._symbol_performance(resolved, oldest_first) for resolved in grounded.resolved_entities]

        return [self._strategy_performance(oldest_first)]

    def _strategy_performance(self, oldest_first: list[PortfolioSnapshot]) -> CapabilityResult:
        if len(oldest_first) < 2:
            return CapabilityResult(
                agent=self.name, description="Not enough history to report performance",
                facts=["I don't have enough recorded history yet to report a return -- at least two snapshots are needed."],
            )

        total_return = _total_return_pct(oldest_first)
        max_drawdown = _max_drawdown_pct(oldest_first)

        facts = [
            f"Over the {len(oldest_first)} recorded cycles I have, total value moved from "
            f"${oldest_first[0].total_value:.2f} to ${oldest_first[-1].total_value:.2f}, "
            f"a {total_return:+.2f}% change."
        ]
        if max_drawdown is not None:
            facts.append(f"The largest peak-to-trough decline over that period was {max_drawdown:.2f}%.")
        facts.append(
            "I don't have a way to compute win rate or per-trade profit/loss -- there's no record "
            "linking a buy to the sell that eventually closes it."
        )

        return CapabilityResult(agent=self.name, description="Reported return and drawdown over recorded history", facts=facts)

    def _symbol_performance(self, resolved, oldest_first: list[PortfolioSnapshot]) -> CapabilityResult:
        symbol = resolved.entity.value
        if not oldest_first:
            return CapabilityResult(
                agent=self.name, description=f"No recorded history for {symbol}",
                facts=[f"I don't have any recorded portfolio history yet to check {symbol} against."],
                affected_entities=[resolved.entity],
            )

        latest_position = oldest_first[-1].positions_json.get(symbol)
        if not latest_position:
            return CapabilityResult(
                agent=self.name, description=f"{symbol} is not currently held",
                facts=[f"{symbol} isn't currently held, so I don't have a return figure for it."],
                affected_entities=[resolved.entity],
            )

        entry = latest_position.get("average_entry_price")
        current = latest_position.get("current_price")
        if not entry or not current:
            return CapabilityResult(
                agent=self.name, description=f"Incomplete position data for {symbol}",
                facts=[f"I don't have complete entry/current price data for {symbol} to compute a return."],
                affected_entities=[resolved.entity],
            )

        unrealized_return = (current - entry) / entry * 100
        fact = (
            f"{symbol}'s unrealized return is {unrealized_return:+.2f}% (entered at ${entry:.2f}, "
            f"currently ${current:.2f})."
        )
        return CapabilityResult(
            agent=self.name, description=f"Reported unrealized return for {symbol}",
            facts=[fact], affected_entities=[resolved.entity],
        )