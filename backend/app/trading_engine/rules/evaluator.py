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
from app.trading_engine.domain.position import Position


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

def evaluate_exit(position: Position, latest_bar: MarketBar, config: StrategyConfig) -> Signal:
    """Evaluate whether an open position should be closed, based on
    config.exit's stop_loss_pct / take_profit_pct against the position's
    entry price. Pure percentage arithmetic, not indicator-based — this
    is why it's a separate function from evaluate_strategy rather than
    another branch of the same AND/OR condition evaluation. Always
    evaluated=True: unlike entry conditions, exit checks need no bar
    history beyond the latest close, so there's no insufficient-data case.
    """
    current_price = latest_bar.close
    entry_price = position.average_entry_price
    triggered: list[str] = []

    stop_loss_pct = config.exit.stop_loss_pct
    if stop_loss_pct is not None:
        stop_price = entry_price * (1 - stop_loss_pct / 100)
        if current_price <= stop_price:
            triggered.append(
                f"stop_loss triggered: price {current_price} <= {stop_price:.4f} "
                f"({stop_loss_pct}% below entry {entry_price})"
            )

    take_profit_pct = config.exit.take_profit_pct
    if take_profit_pct is not None:
        target_price = entry_price * (1 + take_profit_pct / 100)
        if current_price >= target_price:
            triggered.append(
                f"take_profit triggered: price {current_price} >= {target_price:.4f} "
                f"({take_profit_pct}% above entry {entry_price})"
            )

    action = SignalAction.SELL if triggered else SignalAction.HOLD

    return Signal(
        symbol=position.symbol,
        action=action,
        timestamp=latest_bar.timestamp,
        evaluated=True,
        triggered_rules=triggered,
    )