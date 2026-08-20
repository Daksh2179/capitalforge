"""StrategyExplainerAgent: answers "why" questions about past edits,
and now also narrates the WHOLE current strategy in plain English on
request ("what is my strategy doing", "explain my robot").

These are genuinely different questions needing different data: the
per-edit "why" reads ConversationMemory.recent_events (conversational
history); the whole-strategy narration reads the CONFIRMED strategy's
real config (persisted state), which is why this Agent now needs a
database Session -- it never did before.

Distinguishing the two: Grounding's implicit-reference fallback means
resolved_entities is often populated (via memory.primary_focus) even
on a genuinely whole-strategy question like "what is my strategy
doing" asked right after discussing AAPL -- resolved_entities alone
can't tell the two apart. A small, explicit, local marker check on the
raw message ("my strategy", "my robot", etc.) resolves the ambiguity,
same discipline as DetailLevel's own lexical markers -- a documented,
narrow V1 choice, not a general NLU distinction.

V1 scope for the per-edit "why" is honest about what the system
actually knows: if a past edit's ConversationEvent has real reasoning
recorded (currently only the capital-allocation-default case, from
draft_updater.py), report it. Otherwise, correctly say the user
specified the value directly -- never fabricate a technical
justification for a value nobody chose. recent_events is capped at 5
-- an edit older than that genuinely isn't recoverable this way.

Reads Memory read-only via AgentExecutionContext; never writes it.
"""

from sqlalchemy.orm import Session

from app.agent.agent_contracts import AgentName, CapabilityResult
from app.agent.pipeline.types import AgentExecutionContext, DetailLevel
from app.schemas.strategy import AssetRule, CapitalAllocation, ConditionGroup, ExitRules, RuleCondition, StrategyConfig
from app.services import strategy_service

_WHOLE_STRATEGY_MARKERS = [
    "my strategy", "my robot", "my rules", "my setup", "my agent",
    "what is it doing", "what does it do", "explain everything",
]

_OPERATOR_WORDS = {
    "less_than": "drops below", "greater_than": "rises above",
    "price_below": "drops below", "price_above": "rises above",
    "crosses_above": "crosses above", "crosses_below": "crosses below",
    "pct_below": "drops", "pct_above": "rises",
}


def _wants_whole_strategy_explanation(raw_message: str) -> bool:
    lowered = raw_message.lower()
    return any(marker in lowered for marker in _WHOLE_STRATEGY_MARKERS)


def _describe_indicator(indicator: str, period: int) -> str:
    return "the price" if indicator == "PRICE" else f"{indicator}({period})"


def _describe_condition(condition: RuleCondition) -> str:
    left = _describe_indicator(condition.indicator, condition.period)
    verb = _OPERATOR_WORDS.get(condition.operator, condition.operator)
    if condition.compare_indicator is not None and condition.compare_period is not None:
        right = _describe_indicator(condition.compare_indicator, condition.compare_period)
        return f"{left} {verb} {right}"
    if condition.operator in ("pct_below", "pct_above"):
        return f"{left} {verb} {condition.value}%"
    return f"{left} {verb} {condition.value}"


def _describe_condition_group(group: ConditionGroup) -> str:
    if not group.rules:
        return "no conditions set"
    joiner = " and " if group.operator == "AND" else " or "
    return joiner.join(_describe_condition(c) for c in group.rules)


def _describe_capital_allocation(allocation: CapitalAllocation) -> str:
    if allocation.type == "percentage_of_portfolio" and allocation.percentage is not None:
        return f"{allocation.percentage:.0f}% of the portfolio"
    if allocation.type == "fixed_capital" and allocation.capital_usd is not None:
        return f"${allocation.capital_usd:,.2f}"
    if allocation.type == "share_count" and allocation.shares is not None:
        return f"{allocation.shares:.0f} shares"
    return "an unspecified amount"


def _describe_exit(exit_rules: ExitRules) -> str | None:
    parts = []
    if exit_rules.stop_loss_pct is not None:
        parts.append(f"a stop loss at {exit_rules.stop_loss_pct:.0f}%")
    if exit_rules.take_profit_pct is not None:
        parts.append(f"a take profit at {exit_rules.take_profit_pct:.0f}%")
    return " and ".join(parts) if parts else None


def _describe_rule(rule: AssetRule, expanded: bool) -> str:
    buy_text = _describe_condition_group(rule.buy_conditions)
    sell_text = _describe_condition_group(rule.sell_conditions)
    size_text = _describe_capital_allocation(rule.capital_allocation)
    exit_text = _describe_exit(rule.exit)

    if not expanded:
        summary = f"For {rule.symbol}: buy when {buy_text}, using {size_text}."
        if exit_text:
            summary += f" Exits with {exit_text}."
        if sell_text != "no conditions set":
            summary += f" Also sells when {sell_text}."
        return summary

    lines = [
        f"{rule.symbol} -- Buy condition ({rule.buy_conditions.operator}): {buy_text}. "
        f"Sell condition ({rule.sell_conditions.operator}): {sell_text}. "
        f"Position size: {size_text}."
    ]
    if exit_text:
        lines.append(f"Exit rules: {exit_text}.")
    return " ".join(lines)


class StrategyExplainerAgent:
    name = AgentName.STRATEGY_EXPLAINER

    def __init__(self, db: Session) -> None:
        self._db = db

    def execute(self, context: AgentExecutionContext) -> list[CapabilityResult]:
        grounded = context.grounded_context
        memory = context.memory

        if _wants_whole_strategy_explanation(grounded.raw_message):
            return [self._explain_whole_strategy(context)]

        if not grounded.resolved_entities:
            return [CapabilityResult(
                agent=self.name, description="Nothing to explain -- no rule was identified this turn",
                facts=["I'm not sure which rule you're asking about."],
            )]

        results: list[CapabilityResult] = []
        for resolved in grounded.resolved_entities:
            symbol = resolved.entity.value
            matching_event = next(
                (e for e in memory.recent_events if any(ent.value == symbol for ent in e.related_entities)),
                None,
            )

            if matching_event is None:
                results.append(CapabilityResult(
                    agent=self.name, description=f"No recent record of an edit to {symbol}",
                    facts=[f"I don't have a record of a recent change to {symbol} in this conversation."],
                    affected_entities=[resolved.entity],
                ))
                continue

            if matching_event.reasoning:
                fact = f"For {symbol}: {matching_event.reasoning}"
            else:
                fact = f"For {symbol}, you specified that value directly -- I didn't choose it."

            results.append(CapabilityResult(
                agent=self.name, description=f"Explained the {symbol} edit",
                facts=[fact], affected_entities=[resolved.entity],
            ))
        return results

    def _explain_whole_strategy(self, context: AgentExecutionContext) -> CapabilityResult:
        if context.strategy_id is None:
            return CapabilityResult(
                agent=self.name, description="No strategy to explain",
                facts=["I don't have an active strategy to explain right now."],
            )

        strategy = strategy_service.get_strategy(self._db, strategy_id=context.strategy_id)
        if strategy is None or strategy.current_version is None:
            return CapabilityResult(
                agent=self.name, description="No confirmed strategy version found",
                facts=["I don't have a confirmed strategy to explain right now."],
            )

        try:
            config = StrategyConfig.model_validate(strategy.current_version.config_json)
        except Exception:
            return CapabilityResult(
                agent=self.name, description="Could not read strategy config",
                facts=["I couldn't read your strategy's configuration to explain it."],
            )

        if not config.asset_rules:
            return CapabilityResult(
                agent=self.name, description="Strategy has no rules yet",
                facts=["Your strategy doesn't have any rules configured yet."],
            )

        expanded = context.grounded_context.detail_level >= DetailLevel.EXPANDED
        facts = [_describe_rule(rule, expanded) for rule in config.asset_rules]

        portfolio_notes = []
        if config.portfolio_rules.cash_reserve_pct is not None:
            portfolio_notes.append(f"keeps at least {config.portfolio_rules.cash_reserve_pct:.0f}% of the portfolio in cash")
        if config.portfolio_rules.max_allocation_pct is not None:
            portfolio_notes.append(f"never deploys more than {config.portfolio_rules.max_allocation_pct:.0f}% of the portfolio at once")
        if config.portfolio_rules.max_open_positions is not None:
            portfolio_notes.append(f"holds at most {config.portfolio_rules.max_open_positions} position(s) at a time")
        if portfolio_notes:
            facts.append("Overall, your strategy " + ", ".join(portfolio_notes) + ".")

        return CapabilityResult(agent=self.name, description="Explained the whole strategy", facts=facts)