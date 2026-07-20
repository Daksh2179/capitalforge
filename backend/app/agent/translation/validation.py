"""validate_strategy: deterministic checks on a drafted StrategyConfig
before it can be confirmed. No LLM involved — this is exactly the kind
of contradiction/impossible-condition/unintended-logic check that must
never depend on model judgment. Returns every issue found, not just
the first, so a confirmation screen can show the complete picture.
"""

import enum

from pydantic import BaseModel, ConfigDict

from app.schemas.strategy import StrategyConfig


class Severity(str, enum.Enum):
    ERROR = "error"
    WARNING = "warning"


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Severity
    symbol: str | None = None
    message: str


def validate_strategy(config: StrategyConfig) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    issues.extend(_check_has_asset_rules(config))
    for rule in config.asset_rules:
        issues.extend(_check_has_conditions(rule))
        issues.extend(_check_buy_sell_price_contradiction(rule))
        issues.extend(_check_exit_percentage_sanity(rule))
    issues.extend(_check_allocation_over_commitment(config))

    return issues


def _check_has_asset_rules(config: StrategyConfig) -> list[ValidationIssue]:
    if not config.asset_rules:
        return [ValidationIssue(
            severity=Severity.ERROR,
            message="Strategy has no assets configured. Add at least one asset before confirming.",
        )]
    return []


def _check_has_conditions(rule) -> list[ValidationIssue]:
    issues = []
    if not rule.buy_conditions.rules:
        issues.append(ValidationIssue(
            severity=Severity.ERROR, symbol=rule.symbol,
            message=f"{rule.symbol} has no buy conditions. Add at least one condition for when to buy.",
        ))
    if not rule.sell_conditions.rules:
        issues.append(ValidationIssue(
            severity=Severity.ERROR, symbol=rule.symbol,
            message=f"{rule.symbol} has no sell conditions. Add at least one condition for when to sell.",
        ))
    return issues


def _check_buy_sell_price_contradiction(rule) -> list[ValidationIssue]:
    """Only checkable when both sides use a literal PRICE threshold —
    if either side is indicator-based, there's no direct number
    comparison to make, so this check is silently skipped rather than
    guessing."""
    buy_price = _single_literal_price_threshold(rule.buy_conditions, want_upper_bound=True)
    sell_price = _single_literal_price_threshold(rule.sell_conditions, want_upper_bound=False)

    if buy_price is not None and sell_price is not None and buy_price >= sell_price:
        return [ValidationIssue(
            severity=Severity.ERROR, symbol=rule.symbol,
            message=(
                f"{rule.symbol}: buy price (${buy_price}) is not below sell price "
                f"(${sell_price}). This would never produce a valid buy-then-sell cycle."
            ),
        )]
    return []


def _single_literal_price_threshold(group, want_upper_bound: bool) -> float | None:
    """Finds a single PRICE-indicator, literal-value condition in a
    group (less_than for a buy-side upper bound, greater_than for a
    sell-side lower bound). Returns None if the group doesn't have
    exactly this shape — deliberately conservative, not a general
    price-extraction heuristic."""
    price_rules = [
        r for r in group.rules
        if r.indicator == "PRICE" and r.value is not None and r.compare_indicator is None
    ]
    wanted_operator = "less_than" if want_upper_bound else "greater_than"
    matching = [r for r in price_rules if r.operator == wanted_operator]
    if len(matching) == 1:
        return matching[0].value
    return None


def _check_exit_percentage_sanity(rule) -> list[ValidationIssue]:
    issues = []
    stop_loss = rule.exit.stop_loss_pct
    take_profit = rule.exit.take_profit_pct

    if stop_loss is not None and stop_loss >= 100:
        issues.append(ValidationIssue(
            severity=Severity.ERROR, symbol=rule.symbol,
            message=f"{rule.symbol}: stop_loss_pct of {stop_loss}% is invalid (cannot lose more than 100% of a long position).",
        ))

    if stop_loss is not None and take_profit is not None and stop_loss >= take_profit:
        issues.append(ValidationIssue(
            severity=Severity.WARNING, symbol=rule.symbol,
            message=(
                f"{rule.symbol}: stop_loss_pct ({stop_loss}%) is not smaller than "
                f"take_profit_pct ({take_profit}%), an unusual risk/reward setup. "
                f"This is allowed but worth double-checking."
            ),
        ))

    return issues


def _check_allocation_over_commitment(config: StrategyConfig) -> list[ValidationIssue]:
    # Only percentage_of_portfolio allocations are commensurable as a
    # share of the portfolio; fixed_capital and share_count allocations
    # can't be summed into a single percentage, so they're excluded from
    # this over-commitment check (the risk manager enforces the dollar
    # ceilings for those at trade time).
    total_allocation = sum(
        rule.capital_allocation.percentage
        for rule in config.asset_rules
        if rule.capital_allocation.type == "percentage_of_portfolio"
        and rule.capital_allocation.percentage is not None
    )
    max_allocation = config.portfolio_rules.max_allocation_pct

    issues = []
    if total_allocation > 100:
        issues.append(ValidationIssue(
            severity=Severity.ERROR,
            message=(
                f"Total position sizing across all assets is {total_allocation}%, "
                f"which exceeds 100% of the portfolio. Reduce allocations so they sum to 100% or less."
            ),
        ))
    elif max_allocation is not None and total_allocation > max_allocation:
        issues.append(ValidationIssue(
            severity=Severity.WARNING,
            message=(
                f"Total position sizing ({total_allocation}%) exceeds the configured "
                f"max_allocation_pct limit ({max_allocation}%). The risk manager will "
                f"enforce this limit at trade time, but it's worth reconciling now."
            ),
        ))

    return issues