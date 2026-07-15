"""intent_translator: pure, stateless translation of one ParsedIntent
into a small change fragment. No mutation of any draft, no knowledge
of existing state, no persistence, no LLM calls. draft_updater.py
consumes what this produces.
"""

import enum
from dataclasses import dataclass

from app.agent.translation.parsed_intent import ParsedIntent
from app.schemas.strategy import RuleCondition


class FragmentKind(str, enum.Enum):
    BUY_CONDITION = "buy_condition"
    SELL_CONDITION = "sell_condition"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    POSITION_SIZING = "position_sizing"
    PORTFOLIO_RULE = "portfolio_rule"
    REMOVE_ASSET = "remove_asset"
    PAUSE_STRATEGY = "pause_strategy"
    RESUME_STRATEGY = "resume_strategy"
    CLARIFICATION_NEEDED = "clarification_needed"


@dataclass(frozen=True)
class IntentFragment:
    kind: FragmentKind
    symbol: str | None
    raw_text: str
    condition: RuleCondition | None = None
    percentage_value: float | None = None
    portfolio_rule_field: str | None = None
    max_open_positions: int | None = None
    clarification_context: str | None = None


_OPERATION_TO_KIND: dict[str, FragmentKind] = {
    "set_buy_condition": FragmentKind.BUY_CONDITION,
    "set_sell_condition": FragmentKind.SELL_CONDITION,
    "set_stop_loss": FragmentKind.STOP_LOSS,
    "set_take_profit": FragmentKind.TAKE_PROFIT,
    "set_position_sizing": FragmentKind.POSITION_SIZING,
    "set_portfolio_rule": FragmentKind.PORTFOLIO_RULE,
    "remove_asset": FragmentKind.REMOVE_ASSET,
    "pause_strategy": FragmentKind.PAUSE_STRATEGY,
    "resume_strategy": FragmentKind.RESUME_STRATEGY,
    "request_clarification": FragmentKind.CLARIFICATION_NEEDED,
}


def translate_intent(intent: ParsedIntent) -> IntentFragment:
    if intent.intent_type == "subjective" or intent.operation == "request_clarification":
        return IntentFragment(
            kind=FragmentKind.CLARIFICATION_NEEDED,
            symbol=intent.symbol,
            raw_text=intent.raw_text,
            clarification_context=intent.clarification_context,
        )

    kind = _OPERATION_TO_KIND.get(intent.operation)
    if kind is None:
        raise ValueError(f"Unknown operation: {intent.operation}")

    if kind in (FragmentKind.BUY_CONDITION, FragmentKind.SELL_CONDITION):
        condition = _build_condition(intent)
        return IntentFragment(kind=kind, symbol=intent.symbol, raw_text=intent.raw_text, condition=condition)

    if kind in (FragmentKind.STOP_LOSS, FragmentKind.TAKE_PROFIT):
        return IntentFragment(
            kind=kind, symbol=intent.symbol, raw_text=intent.raw_text,
            percentage_value=intent.percentage_value,
        )

    if kind == FragmentKind.POSITION_SIZING:
        return IntentFragment(
            kind=kind, symbol=intent.symbol, raw_text=intent.raw_text,
            percentage_value=intent.percentage_value,
        )

    if kind == FragmentKind.PORTFOLIO_RULE:
        return IntentFragment(
            kind=kind, symbol=None, raw_text=intent.raw_text,
            portfolio_rule_field=intent.portfolio_rule_field,
            percentage_value=intent.percentage_value,
            max_open_positions=intent.max_open_positions,
        )

    # remove_asset, pause_strategy, resume_strategy: symbol/raw_text only
    return IntentFragment(kind=kind, symbol=intent.symbol, raw_text=intent.raw_text)


def _build_condition(intent: ParsedIntent) -> RuleCondition:
    if intent.indicator is None or intent.operator is None:
        raise ValueError(
            f"set_buy_condition/set_sell_condition requires indicator and operator; "
            f"got indicator={intent.indicator}, operator={intent.operator} for: {intent.raw_text!r}"
        )

    if intent.indicator == "PRICE":
        period = 1
    elif intent.period is not None:
        period = intent.period
    else:
        raise ValueError(
            f"set_buy_condition/set_sell_condition requires period for indicator "
            f"'{intent.indicator}' (only PRICE can omit it): {intent.raw_text!r}"
        )

    return RuleCondition(
        indicator=intent.indicator,
        period=period,
        operator=intent.operator,
        value=intent.value,
        compare_indicator=intent.compare_indicator,
        compare_period=intent.compare_period,
    )