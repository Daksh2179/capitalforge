"""draft_updater: applies one IntentFragment to an existing
StrategyConfig (or starts a new one), returning a new StrategyConfig.
Never mutates in place. Owns asset-disambiguation logic: if a fragment
needs a symbol but doesn't have one and multiple assets exist in the
draft, this signals ambiguity rather than guessing.
"""

from dataclasses import dataclass

from app.agent.translation.intent_translator import FragmentKind, IntentFragment
from app.schemas.strategy import (
    AssetRule,
    CapitalAllocation,
    ConditionGroup,
    ExitRules,
    PortfolioRules,
    StrategyConfig,
)

_DEFAULT_ALLOCATION_PCT = 5.0


class AmbiguousAssetError(Exception):
    """Raised when a fragment needs a target asset but none was
    specified and the current draft has more than one candidate."""

    def __init__(self, candidates: list[str]) -> None:
        self.candidates = candidates
        super().__init__(f"Ambiguous target asset among: {candidates}")


@dataclass(frozen=True)
class UpdateOutcome:
    config: StrategyConfig
    description: str


def apply_fragment(draft: StrategyConfig | None, fragment: IntentFragment) -> UpdateOutcome:
    if fragment.kind == FragmentKind.PORTFOLIO_RULE:
        return _apply_portfolio_rule(draft, fragment)

    if fragment.kind in (FragmentKind.PAUSE_STRATEGY, FragmentKind.RESUME_STRATEGY):
        # State transitions belong to Strategy.state (Group 6), not
        # config_json. Nothing to change here; the service layer
        # surfaces this as its own applied_operation without a draft change.
        current = draft or _empty_draft()
        return UpdateOutcome(config=current, description=f"{fragment.kind.value} acknowledged")

    symbol = _resolve_symbol(draft, fragment)

    if fragment.kind == FragmentKind.REMOVE_ASSET:
        return _remove_asset(draft, symbol)

    return _apply_asset_fragment(draft, symbol, fragment)


def _resolve_symbol(draft: StrategyConfig | None, fragment: IntentFragment) -> str:
    if fragment.symbol is not None:
        return fragment.symbol

    existing_symbols = [rule.symbol for rule in draft.asset_rules] if draft else []
    if len(existing_symbols) == 1:
        return existing_symbols[0]

    raise AmbiguousAssetError(candidates=existing_symbols)


def _empty_draft() -> StrategyConfig:
    return StrategyConfig(portfolio_rules=PortfolioRules(), asset_rules=[])


def _describe_allocation(allocation: CapitalAllocation) -> str:
    if allocation.type == "percentage_of_portfolio":
        return f"{allocation.percentage}% of the portfolio"
    if allocation.type == "fixed_capital":
        return f"${allocation.capital_usd}"
    return f"{allocation.shares} shares"


def _empty_asset_rule(symbol: str) -> AssetRule:
    return AssetRule(
        symbol=symbol,
        buy_conditions=ConditionGroup(operator="AND", rules=[]),
        sell_conditions=ConditionGroup(operator="AND", rules=[]),
        capital_allocation=CapitalAllocation(
            type="percentage_of_portfolio", percentage=_DEFAULT_ALLOCATION_PCT
        ),
        exit=ExitRules(),
    )


def _get_or_create_asset_rule(draft: StrategyConfig | None, symbol: str) -> tuple[AssetRule, list[AssetRule]]:
    other_rules = [r for r in draft.asset_rules if r.symbol != symbol] if draft else []
    existing = next((r for r in draft.asset_rules if r.symbol == symbol), None) if draft else None
    return (existing or _empty_asset_rule(symbol)), other_rules

def _merge_condition(existing_rules: list, new_condition) -> list:
    """Replace an existing condition targeting the same
    (indicator, operator, compare_indicator) combination, or append as
    a new condition if no match exists. This is what makes "update
    Apple's buy price to $175" correctly replace the old price
    threshold instead of accumulating a second, conflicting condition,
    while still allowing genuinely different conditions (different
    indicator or operator) to compose together via AND/OR.
    """
    key = (new_condition.indicator, new_condition.operator, new_condition.compare_indicator)
    replaced = False
    updated = []
    for existing in existing_rules:
        existing_key = (existing.indicator, existing.operator, existing.compare_indicator)
        if existing_key == key:
            updated.append(new_condition)
            replaced = True
        else:
            updated.append(existing)
    if not replaced:
        updated.append(new_condition)
    return updated

def _apply_asset_fragment(draft: StrategyConfig | None, symbol: str, fragment: IntentFragment) -> UpdateOutcome:
    rule, other_rules = _get_or_create_asset_rule(draft, symbol)
    portfolio_rules = draft.portfolio_rules if draft else PortfolioRules()

    if fragment.kind == FragmentKind.BUY_CONDITION:
        assert fragment.condition is not None
        new_rules = _merge_condition(rule.buy_conditions.rules, fragment.condition)
        rule = rule.model_copy(update={"buy_conditions": rule.buy_conditions.model_copy(update={"rules": new_rules})})
        description = f"Added buy condition for {symbol}: {fragment.raw_text}"

    elif fragment.kind == FragmentKind.SELL_CONDITION:
        assert fragment.condition is not None
        new_rules = _merge_condition(rule.sell_conditions.rules, fragment.condition)
        rule = rule.model_copy(update={"sell_conditions": rule.sell_conditions.model_copy(update={"rules": new_rules})})
        description = f"Added sell condition for {symbol}: {fragment.raw_text}"

    elif fragment.kind == FragmentKind.STOP_LOSS:
        rule = rule.model_copy(update={"exit": rule.exit.model_copy(update={"stop_loss_pct": fragment.percentage_value})})
        description = f"Set stop loss for {symbol} to {fragment.percentage_value}%"

    elif fragment.kind == FragmentKind.TAKE_PROFIT:
        rule = rule.model_copy(update={"exit": rule.exit.model_copy(update={"take_profit_pct": fragment.percentage_value})})
        description = f"Set take profit for {symbol} to {fragment.percentage_value}%"

    elif fragment.kind == FragmentKind.CAPITAL_ALLOCATION:
        assert fragment.capital_allocation is not None
        rule = rule.model_copy(update={"capital_allocation": fragment.capital_allocation})
        description = f"Set capital allocation for {symbol} to {_describe_allocation(fragment.capital_allocation)}"

    else:
        raise ValueError(f"Unhandled fragment kind in _apply_asset_fragment: {fragment.kind}")

    new_config = StrategyConfig(portfolio_rules=portfolio_rules, asset_rules=[*other_rules, rule])
    return UpdateOutcome(config=new_config, description=description)


def _remove_asset(draft: StrategyConfig | None, symbol: str) -> UpdateOutcome:
    if draft is None:
        raise ValueError(f"Cannot remove {symbol}: draft is empty")
    remaining = [r for r in draft.asset_rules if r.symbol != symbol]
    new_config = StrategyConfig(portfolio_rules=draft.portfolio_rules, asset_rules=remaining)
    return UpdateOutcome(config=new_config, description=f"Removed {symbol} from the strategy")


def _apply_portfolio_rule(draft: StrategyConfig | None, fragment: IntentFragment) -> UpdateOutcome:
    current = draft or _empty_draft()
    field = fragment.portfolio_rule_field

    if field is None:
        raise ValueError(f"set_portfolio_rule requires portfolio_rule_field: {fragment.raw_text!r}")

    if field == "max_open_positions":
        updated = current.portfolio_rules.model_copy(update={"max_open_positions": fragment.max_open_positions})
    else:
        updated = current.portfolio_rules.model_copy(update={field: fragment.percentage_value})

    new_config = StrategyConfig(portfolio_rules=updated, asset_rules=current.asset_rules)
    return UpdateOutcome(config=new_config, description=f"Set {field} to {fragment.percentage_value or fragment.max_open_positions}")