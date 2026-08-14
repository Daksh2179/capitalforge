"""PortfolioAnalystAgent: reads DecisionLog/Order/PortfolioSnapshot --
data the Opportunity Engine has produced correctly every cycle, never
reachable from chat until now. Wraps trading_cycle_service's existing
read functions; the only "new" logic is a one-line symbol filter,
since DecisionLog isn't indexed by symbol at the database layer and a
new query function isn't warranted for a single in-memory filter.

held_position: bool is now set on every per-symbol result -- a real,
deterministic fact (does the latest PortfolioSnapshot currently show
this symbol with positive quantity), added specifically because
InvestmentAnalystAgent's SELL conclusion must never be produced for
an asset the user doesn't actually hold. This is a hard, code-enforced
gate downstream, not just informational -- so this field has to be
trustworthy, not inferred from prose.

V1 scope, deliberately narrow (see docs/decisions.md, "DecisionLog as
evaluation history"):
- "Why didn't you buy/sell X" reports the real, persisted reason
  (plan_outcome/risk_reason) when a buy/sell was actually evaluated
  and blocked. If the condition simply never triggered recently, this
  Agent says so honestly -- it cannot say "RSI was 34, not yet below
  30," because that computed value isn't persisted for HOLD outcomes
  today. Never approximates or guesses that number.
- "How's this strategy doing" reports the most recent PortfolioSnapshot
  (cash, total value, positions) -- NOT performance/returns over time,
  which is PerformanceAnalystAgent's distinct, not-yet-built domain.
"""

import uuid

from sqlalchemy.orm import Session

from app.agent.agent_contracts import AgentName, CapabilityResult
from app.agent.conversation_memory import EntityReference
from app.agent.pipeline.types import AgentExecutionContext
from app.services import strategy_service, trading_cycle_service

_RECENT_LOOKBACK = 50


class PortfolioAnalystAgent:
    name = AgentName.PORTFOLIO_ANALYST

    def __init__(self, db: Session) -> None:
        self._db = db

    def execute(self, context: AgentExecutionContext) -> list[CapabilityResult]:
        grounded = context.grounded_context

        if context.strategy_id is None:
            return [CapabilityResult(
                agent=self.name, description="No active strategy to report on",
                facts=["I don't have an active strategy to look at right now."],
            )]

        strategy = strategy_service.get_strategy(self._db, strategy_id=context.strategy_id)
        if strategy is None or strategy.current_version_id is None:
            return [CapabilityResult(
                agent=self.name, description="No confirmed strategy version found",
                facts=["I don't have a confirmed strategy to look at right now."],
            )]

        if grounded.resolved_entities:
            snapshots = trading_cycle_service.list_portfolio_snapshots(
                self._db, strategy_id=context.strategy_id, limit=1
            )
            latest_positions = snapshots[0].positions_json if snapshots else {}
            return [
                self._explain_symbol(strategy.current_version_id, resolved.entity.value, resolved.entity, latest_positions)
                for resolved in grounded.resolved_entities
            ]

        return [self._summarize_strategy(context.strategy_id)]

    def _explain_symbol(
        self, strategy_version_id: uuid.UUID, symbol: str, entity: EntityReference, latest_positions: dict
    ) -> CapabilityResult:
        held_position = symbol in latest_positions and (latest_positions[symbol].get("quantity", 0) or 0) > 0

        logs = trading_cycle_service.list_decision_logs(
            self._db, strategy_version_id=strategy_version_id, limit=_RECENT_LOOKBACK
        )
        symbol_logs = [log for log in logs if log.market_snapshot_json.get("symbol") == symbol]

        if not symbol_logs:
            return CapabilityResult(
                agent=self.name, description=f"No recent evaluation history for {symbol}",
                facts=[f"I don't have any recent evaluation history for {symbol}."],
                affected_entities=[entity], held_position=held_position,
            )

        most_recent = symbol_logs[0]  # already ordered newest-first

        if most_recent.action_taken == "buy" and most_recent.risk_approved:
            fact = f"{symbol} was actually bought recently, not skipped."
        elif most_recent.action_taken in ("buy", "sell"):
            fact = (
                f"{symbol}'s {most_recent.action_taken} condition triggered recently, "
                f"but it wasn't executed: {most_recent.risk_reason}"
            )
        else:
            fact = (
                f"{symbol}'s buy/sell conditions haven't triggered recently, based on the last "
                f"{len(symbol_logs)} evaluation(s) I have on record."
            )

        return CapabilityResult(
            agent=self.name, description=f"Reported recent evaluation history for {symbol}",
            facts=[fact], affected_entities=[entity], held_position=held_position,
        )

    def _summarize_strategy(self, strategy_id: uuid.UUID) -> CapabilityResult:
        snapshots = trading_cycle_service.list_portfolio_snapshots(self._db, strategy_id=strategy_id, limit=1)
        if not snapshots:
            return CapabilityResult(
                agent=self.name, description="No portfolio snapshot recorded yet",
                facts=["I don't have a recorded portfolio snapshot yet -- the strategy may not have completed a full cycle."],
            )

        snapshot = snapshots[0]
        held = ", ".join(snapshot.positions_json.keys()) or "no open positions"
        fact = (
            f"As of the last recorded cycle, cash was ${snapshot.cash_balance:.2f} and total value was "
            f"${snapshot.total_value:.2f}, holding: {held}."
        )
        return CapabilityResult(agent=self.name, description="Summarized current portfolio state", facts=[fact])