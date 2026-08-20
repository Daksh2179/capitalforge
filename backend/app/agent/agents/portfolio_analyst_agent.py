"""PortfolioAnalystAgent: reads the user's watchlist (portfolio_service),
DecisionLog/Order/PortfolioSnapshot history, and current holdings --
and now DECLARES (never performs) additions/removals to the
portfolio-in-progress, via the narrow PortfolioChange contract.

Watchlist is checked FIRST and ALWAYS, regardless of whether an active
strategy exists.

Add/remove detection is a small, explicit, local lexical check (same
discipline as DetailLevel's own markers) -- verb + portfolio-noun,
checked independently so the symbol sitting between them doesn't break
the match. A message must ALSO successfully resolve to a real entity
before a PortfolioChange is even considered, which meaningfully
narrows accidental misfires. The operation itself is genuinely
low-stakes and instantly reversible (just say the opposite), and the
response always states plainly what happened, so a misfire is
immediately visible and correctable, never silently wrong.

Three locked safety/product decisions:
1. If a symbol has BOTH a portfolio-in-progress entry AND a confirmed
   AI rule, "remove X" is genuinely ambiguous -- raises a real
   clarification (which action), never guesses.
2. Portfolio-in-progress membership and rule creation are deliberately
   NEVER auto-synced. Creating a rule never silently adds a portfolio
   item, and vice versa -- "add X and buy it when RSI<30" produces two
   independent, separately-reported results this turn, not one hidden
   coupling.
3. This capability has NO authority to place sell orders, ever. If the
   symbol is actually held (checked against the real latest
   PortfolioSnapshot), removal proceeds, but a limitation is always
   attached stating plainly that this does not sell the position or
   touch its AI rule.

Strategy health (opportunity/selection/deferral counts) is folded into
the same "how's my strategy doing" summary.

V1 scope, deliberately narrow (see docs/decisions.md, "DecisionLog as
evaluation history"): "why didn't you buy/sell X" reports the real,
persisted reason when a buy/sell was actually evaluated and blocked.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.agent.agent_contracts import (
    AgentName,
    CapabilityResult,
    ClarificationRequest,
    PortfolioChange,
    PortfolioChangeType,
)
from app.agent.conversation_memory import EntityReference
from app.agent.pipeline.types import AgentExecutionContext, ResolvedEntity
from app.services import portfolio_service, strategy_service, trading_cycle_service

_RECENT_LOOKBACK = 50

_ADD_VERBS = ["add", "start tracking", "put"]
_REMOVE_VERBS = ["remove", "stop tracking", "take off", "delete"]
_PORTFOLIO_NOUNS = ["portfolio", "watchlist", "list", "setup"]


def _wants_portfolio_add(raw_message: str) -> bool:
    lowered = raw_message.lower()
    return any(verb in lowered for verb in _ADD_VERBS) and any(noun in lowered for noun in _PORTFOLIO_NOUNS)


def _wants_portfolio_remove(raw_message: str) -> bool:
    lowered = raw_message.lower()
    return any(verb in lowered for verb in _REMOVE_VERBS) and any(noun in lowered for noun in _PORTFOLIO_NOUNS)


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
            results: list[CapabilityResult] = []
            for resolved in grounded.resolved_entities:
                mutation_result = self._handle_add_remove(context, resolved)
                results.append(
                    mutation_result if mutation_result is not None
                    else self._explain_symbol(context, resolved.entity.value, resolved.entity, watchlist)
                )
            return results

        return [self._summarize(context, watchlist)]

    def _handle_add_remove(self, context: AgentExecutionContext, resolved: ResolvedEntity) -> CapabilityResult | None:
        symbol = resolved.entity.value
        raw_message = context.grounded_context.raw_message

        if _wants_portfolio_add(raw_message):
            return CapabilityResult(
                agent=self.name, description=f"Adding {symbol} to your portfolio",
                facts=[f"Adding {symbol} to your portfolio list."],
                affected_entities=[resolved.entity],
                portfolio_change=PortfolioChange(change_type=PortfolioChangeType.ADD, symbol=symbol),
            )

        if _wants_portfolio_remove(raw_message):
            on_watchlist = context.user_id is not None and any(
                h.symbol == symbol for h in portfolio_service.list_holdings(self._db, user_id=context.user_id)
            )
            has_rule = context.user_id is not None and portfolio_service.is_symbol_ai_configured(
                self._db, user_id=context.user_id, symbol=symbol
            )

            if on_watchlist and has_rule:
                return CapabilityResult(
                    agent=self.name, description=f"Needs clarification on removing {symbol}",
                    clarification=ClarificationRequest(
                        question_text=(
                            f"{symbol} is both on your portfolio list and has an AI-managed rule. "
                            f"Do you want to remove it from your portfolio entirely, or just remove its "
                            f"AI rule and keep it on your list?"
                        ),
                        candidates=["remove from portfolio entirely", "remove just the AI rule"],
                        about=resolved.entity,
                    ),
                    affected_entities=[resolved.entity],
                )

            limitations = []
            if self._is_held(context.strategy_id, symbol):
                limitations.append(
                    f"Removing {symbol} from your portfolio list does not sell your existing shares "
                    f"or change any AI rule managing it."
                )

            return CapabilityResult(
                agent=self.name, description=f"Removing {symbol} from your portfolio",
                facts=[f"Removing {symbol} from your portfolio list."],
                affected_entities=[resolved.entity], limitations=limitations,
                portfolio_change=PortfolioChange(change_type=PortfolioChangeType.REMOVE, symbol=symbol),
            )

        return None

    def _is_held(self, strategy_id, symbol: str) -> bool:
        if strategy_id is None:
            return False
        snapshots = trading_cycle_service.list_portfolio_snapshots(self._db, strategy_id=strategy_id, limit=1)
        if not snapshots:
            return False
        positions = snapshots[0].positions_json
        return symbol in positions and (positions[symbol].get("quantity", 0) or 0) > 0

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
                held_position = self._is_held(context.strategy_id, symbol)

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

            health_fact = self._summarize_health(context.strategy_id)
            if health_fact:
                facts.append(health_fact)

        if not facts:
            facts.append("You don't have anything on your watchlist or an active strategy yet.")

        return CapabilityResult(agent=self.name, description="Summarized portfolio and watchlist", facts=facts)

    def _summarize_health(self, strategy_id) -> str | None:
        strategy = strategy_service.get_strategy(self._db, strategy_id=strategy_id)
        if strategy is None or strategy.current_version_id is None:
            return None

        logs = trading_cycle_service.list_decision_logs(
            self._db, strategy_version_id=strategy.current_version_id, limit=_RECENT_LOOKBACK
        )
        if not logs:
            return None

        buy_logs = [log for log in logs if log.action_taken == "buy"]
        sell_logs = [log for log in logs if log.action_taken == "sell"]
        hold_count = sum(1 for log in logs if log.action_taken == "hold")

        executed = sum(1 for log in buy_logs if log.plan_outcome == "selected" and log.risk_approved)
        blocked_after_selection = sum(1 for log in buy_logs if log.plan_outcome == "selected" and not log.risk_approved)
        deferred = sum(1 for log in buy_logs if log.plan_outcome == "deferred")
        skipped_liquidity = sum(1 for log in buy_logs if log.plan_outcome == "skipped_liquidity")
        sells_executed = sum(1 for log in sell_logs if log.risk_approved)
        sells_blocked = sum(1 for log in sell_logs if not log.risk_approved)

        parts = [f"Over the last {len(logs)} evaluation(s) I have on record: {hold_count} resulted in no action"]
        if buy_logs:
            detail = (
                f"{executed} executed, {deferred} deferred due to capital competition, "
                f"{skipped_liquidity} skipped for liquidity"
            )
            if blocked_after_selection:
                detail += f", {blocked_after_selection} selected but blocked at execution"
            parts.append(f"{len(buy_logs)} buy condition(s) triggered ({detail})")
        if sell_logs:
            parts.append(f"{len(sell_logs)} sell condition(s) triggered ({sells_executed} executed, {sells_blocked} blocked)")

        summary = ", ".join(parts) + "."

        triggering_logs = [log for log in logs if log.action_taken in ("buy", "sell")]
        if triggering_logs:
            days_since = (datetime.now(timezone.utc) - triggering_logs[0].timestamp).days
            summary += f" The most recent buy/sell trigger was {days_since} day(s) ago."
        else:
            summary += " No buy or sell condition has triggered in the recorded history I have."

        return summary