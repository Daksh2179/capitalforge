"""Indicator registry: resolves a strategy config's indicator name
(e.g. "RSI") to its calculation function. First real consumer: the
rule evaluator.
"""

from collections.abc import Callable

from app.trading_engine.domain.market_bar import MarketBar
from app.trading_engine.indicators.ema import calculate_ema
from app.trading_engine.indicators.price import calculate_price
from app.trading_engine.indicators.rolling_high import calculate_rolling_high
from app.trading_engine.indicators.rsi import calculate_rsi
from app.trading_engine.indicators.sma import calculate_sma

IndicatorFunc = Callable[[list[MarketBar], int], list[float | None]]

INDICATOR_REGISTRY: dict[str, IndicatorFunc] = {
    "PRICE": calculate_price,
    "RSI": calculate_rsi,
    "SMA": calculate_sma,
    "EMA": calculate_ema,
    "ROLLING_HIGH": calculate_rolling_high,
}


def resolve_indicator(name: str) -> IndicatorFunc:
    try:
        return INDICATOR_REGISTRY[name]
    except KeyError as e:
        raise ValueError(f"Unknown indicator: {name}") from e