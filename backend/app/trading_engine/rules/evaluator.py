"""Rule evaluator: consumes MarketBar history + an AssetRule and
produces a Signal describing whether its buy or sell conditions
currently hold.

evaluate_strategy checks buy_conditions against a flat asset (no open
position). evaluate_exit checks sell_conditions against an open
Position, merged with the percentage stop_loss_pct/take_profit_pct
safety net. The percentage safety net, when configured, is always
evaluable (needs only the latest close and entry price) regardless of
whether sell_conditions can resolve — so evaluated is True whenever
either mechanism is checkable, and False only when sell_conditions
lack sufficient history AND no percentage safety net is configured.
"""

from datetime import datetime, timezone

from app.schemas.strategy import AssetRule, ConditionGroup, RuleCondition
from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.domain.position import Position
from app.trading_engine.domain.signal import Signal, SignalAction
from app.trading_engine.indicators.registry import resolve_indicator


def evaluate_strategy(bars: list[MarketBar], rule: AssetRule) -> Signal:
    """Evaluate rule.buy_conditions against the latest available bar."""
    if not bars:
        return Signal(
            symbol=rule.symbol, action=SignalAction.HOLD,
            timestamp=datetime.now(timezone.utc), evaluated=False, triggered_rules=[],
        )

    latest_bar = bars[-1]
    combined, triggered = _evaluate_group(bars, rule.buy_conditions)

    if combined is None:
        return Signal(
            symbol=rule.symbol, action=SignalAction.HOLD,
            timestamp=latest_bar.timestamp, evaluated=False, triggered_rules=[],
        )

    action = SignalAction.BUY if combined else SignalAction.HOLD
    return Signal(
        symbol=rule.symbol, action=action, timestamp=latest_bar.timestamp,
        evaluated=True, triggered_rules=triggered,
    )


def evaluate_exit(position: Position, bars: list[MarketBar], rule: AssetRule) -> Signal:
    """Evaluate whether an open position should be closed: rule.sell_conditions
    (indicator-based, may need history) merged with rule.exit's percentage
    stop_loss_pct/take_profit_pct (always evaluable when configured, needs
    only the latest close and entry price).
    """
    if not bars:
        return Signal(
            symbol=position.symbol, action=SignalAction.HOLD,
            timestamp=datetime.now(timezone.utc), evaluated=False, triggered_rules=[],
        )

    latest_bar = bars[-1]
    triggered: list[str] = []

    rule_combined, rule_triggered = _evaluate_group(bars, rule.sell_conditions)
    rule_evaluated = rule_combined is not None
    if rule_evaluated and rule_combined:
        triggered.extend(rule_triggered)

    percentage_configured = rule.exit.stop_loss_pct is not None or rule.exit.take_profit_pct is not None
    if percentage_configured:
        triggered.extend(_evaluate_percentage_exit(position, latest_bar, rule))

    evaluated = rule_evaluated or percentage_configured

    if not evaluated:
        return Signal(
            symbol=position.symbol, action=SignalAction.HOLD,
            timestamp=latest_bar.timestamp, evaluated=False, triggered_rules=[],
        )

    action = SignalAction.SELL if triggered else SignalAction.HOLD
    return Signal(
        symbol=position.symbol, action=action, timestamp=latest_bar.timestamp,
        evaluated=True, triggered_rules=triggered,
    )


def _evaluate_percentage_exit(position: Position, latest_bar: MarketBar, rule: AssetRule) -> list[str]:
    current_price = latest_bar.close
    entry_price = position.average_entry_price
    triggered: list[str] = []

    stop_loss_pct = rule.exit.stop_loss_pct
    if stop_loss_pct is not None:
        stop_price = entry_price * (1 - stop_loss_pct / 100)
        if current_price <= stop_price:
            triggered.append(
                f"stop_loss triggered: price {current_price} <= {stop_price:.4f} "
                f"({stop_loss_pct}% below entry {entry_price})"
            )

    take_profit_pct = rule.exit.take_profit_pct
    if take_profit_pct is not None:
        target_price = entry_price * (1 + take_profit_pct / 100)
        if current_price >= target_price:
            triggered.append(
                f"take_profit triggered: price {current_price} >= {target_price:.4f} "
                f"({take_profit_pct}% above entry {entry_price})"
            )

    return triggered


def _evaluate_group(bars: list[MarketBar], group: ConditionGroup) -> tuple[bool | None, list[str]]:
    results: list[bool] = []
    triggered: list[str] = []

    for rule in group.rules:
        outcome, description = _evaluate_rule(bars, rule)
        if outcome is None:
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

    if rule.operator == "price_above":
        outcome = latest_close > latest_value
        return outcome, f"price {latest_close} above {rule.indicator}({rule.period})={latest_value:.4f}"

    if rule.operator == "price_below":
        outcome = latest_close < latest_value
        return outcome, f"price {latest_close} below {rule.indicator}({rule.period})={latest_value:.4f}"

    if rule.operator in ("less_than", "greater_than"):
        target, target_desc = _resolve_target(bars, rule)
        if target is None:
            return None, ""
        outcome = latest_value < target if rule.operator == "less_than" else latest_value > target
        return outcome, (
            f"{rule.indicator}({rule.period}) {rule.operator} {target_desc} "
            f"(actual={latest_value:.4f})"
        )

    if rule.operator in ("crosses_above", "crosses_below"):
        if len(values) < 2:
            return None, ""
        prev_value = values[-2]
        if prev_value is None:
            return None, ""
        target_now, target_desc = _resolve_target(bars, rule)
        target_prev, _ = _resolve_target(bars[:-1], rule)
        if target_now is None or target_prev is None:
            return None, ""
        was_below = prev_value < target_prev
        was_above = prev_value > target_prev
        is_below = latest_value < target_now
        is_above = latest_value > target_now
        outcome = (was_below and is_above) if rule.operator == "crosses_above" else (was_above and is_below)
        return outcome, (
            f"{rule.indicator}({rule.period}) {rule.operator} {target_desc} "
            f"(prev={prev_value:.4f}, now={latest_value:.4f})"
        )

    if rule.operator in ("pct_below", "pct_above"):
        if rule.value is None:
            return None, ""
        pct = rule.value
        if rule.operator == "pct_below":
            threshold = latest_value * (1 - pct / 100)
            outcome = latest_close <= threshold
        else:
            threshold = latest_value * (1 + pct / 100)
            outcome = latest_close >= threshold
        return outcome, (
            f"price {latest_close} {rule.operator} {pct}% of "
            f"{rule.indicator}({rule.period})={latest_value:.4f} (threshold={threshold:.4f})"
        )

    raise ValueError(f"Unknown operator: {rule.operator}")


def _resolve_target(bars: list[MarketBar], rule: RuleCondition) -> tuple[float | None, str]:
    """Resolve what a level/crossover comparison is checked against:
    either a literal value, or another indicator's latest value over
    the given bars window."""
    if rule.compare_indicator is not None:
        if not bars or rule.compare_period is None:
            return None, ""
        compare_func = resolve_indicator(rule.compare_indicator)
        compare_values = compare_func(bars, rule.compare_period)
        compare_latest = compare_values[-1]
        if compare_latest is None:
            return None, ""
        return compare_latest, f"{rule.compare_indicator}({rule.compare_period})={compare_latest:.4f}"

    if rule.value is not None:
        return rule.value, str(rule.value)

    return None, ""