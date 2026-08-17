"""PortfolioAnalystAgent: reads the user's watchlist (portfolio_service),
DecisionLog/Order/PortfolioSnapshot history, and current holdings --
the fullest picture of "what's going on with my portfolio" this system
can honestly give.

Watchlist is checked FIRST and ALWAYS, regardless of whether an active
strategy exists -- someone who's only staged symbols and never
confirmed a strategy deserves a real, useful answer, not "I don't have
an active strategy." This was a confirmed, real gap: the watchlist
(portfolio_service) and the Agent architecture had never been
connected to each other at all before this.

Distinct from PerformanceAnalystAgent's "how has it performed over
time" -- this Agent answers "what's the current picture," not trends.

V1 scope, deliberately narrow (see docs/decisions.md, "DecisionLog as
evaluation history"): "why didn't you buy/sell X" reports the real,
persisted reason when a buy/sell was actually evaluated and blocked.
If a condition simply never triggered, this Agent says so honestly --
it cannot say "RSI was 34, not yet below 30," since that computed
value isn't persisted for HOLD outcomes today.
"""


from sqlalchemy.orm import Session

from app.agent.agent_contracts import AgentName, CapabilityResult
from app.agent.conversation_memory import EntityReference
from app.agent.pipeline.types import AgentExecutionContext
from app.services import portfolio_service, strategy_service, trading_cycle_service

_RECENT_LOOKBACK = 50


class PortfolioAnalystAgent:
    name = AgentName.PORTFOLIO_ANALYST

    def __init__(self, db: Session) -> None:
        self._db = db

    def execute(self, context: AgentExecutionContext) -> list[CapabilityResult]:
        grounded = context.grounded_context
        watchlist = (
            portfolio_service.list_holdings(self._db, user_id=context.user_id)
            if context.user_id is not None else []
        )

        if grounded.resolved_entities:
            return [
                self._explain_symbol(context, resolved.entity.value, resolved.entity, watchlist)
                for resolved in grounded.resolved_entities
            ]

        return [self._summarize(context, watchlist)]

    def _explain_symbol(
        self, context: AgentExecutionContext, symbol: str, entity: EntityReference, watchlist: list
    ) -> CapabilityResult:
        facts: list[str] = []
        on_watchlist = any(h.symbol == symbol for h in watchlist)

        if on_watchlist and context.user_id is not None:
            configured = portfolio_service.is_symbol_ai_configured(self._db, user_id=context.user_id, symbol=symbol)
            facts.append(
                f"{symbol} is on your watchlist and already has an AI-managed rule."
                if configured else
                f"{symbol} is on your watchlist but doesn't have an AI-managed rule yet."
            )

        held_position: bool | None = None
        if context.strategy_id is not None:
            strategy = strategy_service.get_strategy(self._db, strategy_id=context.strategy_id)
            if strategy is not None and strategy.current_version_id is not None:
                snapshots = trading_cycle_service.list_portfolio_snapshots(
                    self._db, strategy_id=context.strategy_id, limit=1
                )
                latest_positions = snapshots[0].positions_json if snapshots else {}
                held_position = symbol in latest_positions and (latest_positions[symbol].get("quantity", 0) or 0) > 0

                logs = trading_cycle_service.list_decision_logs(
                    self._db, strategy_version_id=strategy.current_version_id, limit=_RECENT_LOOKBACK
                )
                symbol_logs = [log for log in logs if log.market_snapshot_json.get("symbol") == symbol]
                if symbol_logs:
                    most_recent = symbol_logs[0]
                    if most_recent.action_taken == "buy" and most_recent.risk_approved:
                        facts.append(f"{symbol} was actually bought recently, not skipped.")
                    elif most_recent.action_taken in ("buy", "sell"):
                        facts.append(
                            f"{symbol}'s {most_recent.action_taken} condition triggered recently, "
                            f"but it wasn't executed: {most_recent.risk_reason}"
                        )
                    else:
                        facts.append(
                            f"{symbol}'s buy/sell conditions haven't triggered recently, based on the last "
                            f"{len(symbol_logs)} evaluation(s) I have on record."
                        )

        if not facts:
            facts.append(
                f"{symbol} is on your watchlist, but I don't have any evaluation history for it yet."
                if on_watchlist else
                f"I don't have any information on {symbol} in your portfolio or watchlist."
            )

        return CapabilityResult(
            agent=self.name, description=f"Reported on {symbol}",
            facts=facts, affected_entities=[entity], held_position=held_position,
        )

    def _summarize(self, context: AgentExecutionContext, watchlist: list) -> CapabilityResult:
        facts: list[str] = []

        if watchlist:
            configured: list[str] = []
            unconfigured: list[str] = []
            for holding in watchlist:
                is_configured = (
                    portfolio_service.is_symbol_ai_configured(self._db, user_id=context.user_id, symbol=holding.symbol)
                    if context.user_id is not None else False
                )
                (configured if is_configured else unconfigured).append(holding.symbol)
            if unconfigured:
                facts.append(f"On your watchlist without an AI-managed rule yet: {', '.join(unconfigured)}.")
            if configured:
                facts.append(f"On your watchlist with an AI-managed rule already: {', '.join(configured)}.")

        if context.strategy_id is not None:
            snapshots = trading_cycle_service.list_portfolio_snapshots(
                self._db, strategy_id=context.strategy_id, limit=1
            )
            if snapshots:
                snapshot = snapshots[0]
                held = ", ".join(snapshot.positions_json.keys()) or "no open positions"
                facts.append(
                    f"As of the last recorded cycle, cash was ${snapshot.cash_balance:.2f} and total value was "
                    f"${snapshot.total_value:.2f}, holding: {held}."
                )
            else:
                facts.append(
                    "I don't have a recorded portfolio snapshot yet -- the strategy may not have completed a full cycle."
                )

        if not facts:
            facts.append("You don't have anything on your watchlist or an active strategy yet.")

        return CapabilityResult(agent=self.name, description="Summarized portfolio and watchlist", facts=facts)