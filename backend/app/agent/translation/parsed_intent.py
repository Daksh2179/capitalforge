"""ParsedIntent: the flat, LLM-facing intermediate schema. The LLM's
only job is to produce these — deterministic code (intent_translator,
draft_updater) does everything else. Designed around operations, not
just buy/sell, so future commands (pause, allocation changes, removing
an asset) fit without redesigning this schema.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

Operation = Literal[
    "set_buy_condition",
    "set_sell_condition",
    "set_stop_loss",
    "set_take_profit",
    "set_capital_allocation",
    "set_portfolio_rule",
    "remove_asset",
    "pause_strategy",
    "resume_strategy",
    "request_clarification",
    "request_information",
]

AllocationType = Literal["percentage_of_portfolio", "fixed_capital", "share_count"]

IntentType = Literal["objective", "subjective"]

Indicator = Literal["PRICE", "RSI", "SMA", "EMA", "ROLLING_HIGH"]

ConditionOperator = Literal[
    "less_than", "greater_than", "price_above", "price_below",
    "crosses_above", "crosses_below", "pct_below", "pct_above",
]

PortfolioRuleField = Literal["cash_reserve_pct", "max_allocation_pct", "max_open_positions"]


class ParsedIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Operation
    intent_type: IntentType
    symbol: str | None = None

    indicator: Indicator | None = None
    period: int | None = None
    operator: ConditionOperator | None = None
    value: float | None = None
    compare_indicator: Indicator | None = None
    compare_period: int | None = None

    percentage: float | None = None
    allocation_type: AllocationType | None = None
    capital_usd: float | None = None
    shares: float | None = None
    portfolio_rule_field: PortfolioRuleField | None = None
    max_open_positions: int | None = None

    clarification_context: str | None = None
    raw_text: str


class IntentBatch(BaseModel):
    """Top-level LLM response shape — Groq's structured output must be
    a single object, not a bare array, hence this wrapper."""

    model_config = ConfigDict(extra="forbid")

    intents: list[ParsedIntent]