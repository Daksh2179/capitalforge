"""Pydantic schemas for strategy requests/responses."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.strategy import StrategyState, StrategyVersionSource

# --- Rule config schema (the shape of StrategyVersion.config_json) ---


class RuleCondition(BaseModel):
    """A single condition, e.g. RSI(14) < 30, or EMA(20) crosses_above EMA(50).

    Exactly one of `value` or `compare_indicator` should be set for
    operators that need a comparison target (less_than, greater_than,
    crosses_above, crosses_below, pct_below, pct_above). price_above/
    price_below need neither — they always compare against the bar's
    own close price implicitly.
    """

    model_config = ConfigDict(extra="forbid")

    indicator: Literal["PRICE", "RSI", "SMA", "EMA", "ROLLING_HIGH"]
    period: int = Field(gt=0)
    operator: Literal[
        "less_than",
        "greater_than",
        "price_above",
        "price_below",
        "crosses_above",
        "crosses_below",
        "pct_below",
        "pct_above",
    ]
    value: float | None = None
    compare_indicator: Literal["PRICE", "RSI", "SMA", "EMA", "ROLLING_HIGH"] | None = None
    compare_period: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _validate_comparison_target(self) -> "RuleCondition":
        needs_target = self.operator in (
            "less_than", "greater_than", "crosses_above", "crosses_below",
            "pct_below", "pct_above",
        )
        has_value = self.value is not None
        has_compare_indicator = self.compare_indicator is not None

        if needs_target and not has_value and not has_compare_indicator:
            raise ValueError(
                f"Operator '{self.operator}' requires either 'value' or "
                f"'compare_indicator' to be set"
            )
        if has_value and has_compare_indicator:
            raise ValueError(
                "Only one of 'value' or 'compare_indicator' may be set, not both"
            )
        if has_compare_indicator and self.compare_period is None:
            raise ValueError("'compare_period' is required when 'compare_indicator' is set")
        return self


class ConditionGroup(BaseModel):
    """A group of conditions combined with AND/OR."""

    model_config = ConfigDict(extra="forbid")

    operator: Literal["AND", "OR"]
    rules: list[RuleCondition] = Field(min_length=1)


class PositionSizing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["fixed_allocation"]
    value_pct: float = Field(gt=0, le=100)


class ExitRules(BaseModel):
    """Percentage-based safety net, layered on top of sell_conditions,
    not the sole exit mechanism."""

    model_config = ConfigDict(extra="forbid")

    stop_loss_pct: float | None = Field(default=None, gt=0)
    take_profit_pct: float | None = Field(default=None, gt=0)


class AssetRule(BaseModel):
    """Trading rules for a single asset within a Portfolio Strategy."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=10)
    buy_conditions: ConditionGroup
    sell_conditions: ConditionGroup
    position_sizing: PositionSizing
    exit: ExitRules


class PortfolioRules(BaseModel):
    """Portfolio-wide constraints, distinct from any single AssetRule.
    All fields optional: unset fields fall back to engine defaults
    (see RiskLimits) rather than forcing every strategy to specify
    every limit explicitly.
    """

    model_config = ConfigDict(extra="forbid")

    cash_reserve_pct: float | None = Field(default=None, ge=0, le=100)
    max_allocation_pct: float | None = Field(default=None, gt=0, le=100)
    max_open_positions: int | None = Field(default=None, gt=0)


class StrategyConfig(BaseModel):
    """The full structured shape of a Portfolio Strategy, stored as
    StrategyVersion.config_json. schema_version allows this shape to
    evolve over time without requiring a database migration.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2] = 2
    portfolio_rules: PortfolioRules
    asset_rules: list[AssetRule] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_unique_symbols(self) -> "StrategyConfig":
        symbols = [rule.symbol for rule in self.asset_rules]
        if len(symbols) != len(set(symbols)):
            raise ValueError("Each symbol may only appear once in asset_rules")
        return self


# --- API request/response schemas ---


class StrategyCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    config: StrategyConfig
    source: StrategyVersionSource = StrategyVersionSource.MANUAL


class StrategyVersionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: StrategyConfig
    source: StrategyVersionSource = StrategyVersionSource.MANUAL


class StrategyVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_id: uuid.UUID
    version_number: int
    config_json: dict
    source: StrategyVersionSource
    confirmed_at: datetime | None
    created_at: datetime


class StrategyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    state: StrategyState
    current_version_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime