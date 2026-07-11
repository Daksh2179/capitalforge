"""Rule evaluator: consumes MarketBar history + a StrategyConfig and
produces a Signal describing whether the configured entry conditions
currently hold.

V1 scope: only entry conditions (StrategyConfig.conditions) are
evaluated here. Exit conditions (stop_loss_pct / take_profit_pct) are
percentage-based against an open position's entry price, not
indicator-based — the risk manager evaluates those against a live
Position, not this module. Consequently this evaluator only ever
produces BUY or HOLD, never SELL.
"""

from datetime import datetime, timezone

from app.schemas.strategy import ConditionGroup, RuleCondition, StrategyConfig
from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.domain.signal import Signal, SignalAction
from app.trading_engine.indicators.registry import resolve_indicator


def evaluate_strategy(bars: list[MarketBar], config: StrategyConfig) -> Signal:
    """Evaluate config.conditions against the latest available bar."""
    if not bars:
        return Signal(
            symbol=config.symbol,
            action=SignalAction.HOLD,
            timestamp=datetime.now(timezone.utc),
            evaluated=False,
            triggered_rules=[],
        )

    latest_bar = bars[-1]
    combined, triggered = _evaluate_group(bars, config.conditions)

    if combined is None:
        return Signal(
            symbol=config.symbol,
            action=SignalAction.HOLD,
            timestamp=latest_bar.timestamp,
            evaluated=False,
            triggered_rules=[],
        )

    action = SignalAction.BUY if combined else SignalAction.HOLD

    return Signal(
        symbol=config.symbol,
        action=action,
        timestamp=latest_bar.timestamp,
        evaluated=True,
        triggered_rules=triggered,
    )


def _evaluate_group(
    bars: list[MarketBar], group: ConditionGroup
) -> tuple[bool | None, list[str]]:
    results: list[bool] = []
    triggered: list[str] = []

    for rule in group.rules:
        outcome, description = _evaluate_rule(bars, rule)
        if outcome is None:
            # Any rule lacking enough history makes the whole group
            # unable to evaluate — never silently treated as False.
            return None, []
        results.append(outcome)
        if outcome:
            triggered.append(description)

    combined = all(results) if group.operator == "AND" else any(results)
    return combined, triggered


def _evaluate_rule(bars: list[MarketBar], rule: RuleCondition) -> tuple[bool | None, str]:
    indicator_func = resolve_indicator(rule.indicator)
    values = indicator_func(bars, rule.period)
    latest_value = values[-1]

    if latest_value is None:
        return None, ""

    latest_close = bars[-1].close

    if rule.operator in ("less_than", "greater_than"):
        if rule.value is None:
            raise ValueError(
                f"Rule operator '{rule.operator}' requires a value, got None "
                f"for indicator {rule.indicator}({rule.period})"
            )
        threshold: float = rule.value

        if rule.operator == "less_than":
            outcome = latest_value < threshold
            description = f"{rule.indicator}({rule.period}) < {threshold} (actual={latest_value:.4f})"
        else:
            outcome = latest_value > threshold
            description = f"{rule.indicator}({rule.period}) > {threshold} (actual={latest_value:.4f})"
    elif rule.operator == "price_above":
        outcome = latest_close > latest_value
        description = f"price {latest_close} above {rule.indicator}({rule.period})={latest_value:.4f}"
    elif rule.operator == "price_below":
        outcome = latest_close < latest_value
        description = f"price {latest_close} below {rule.indicator}({rule.period})={latest_value:.4f}"
    else:
        raise ValueError(f"Unknown operator: {rule.operator}")

    return outcome, description