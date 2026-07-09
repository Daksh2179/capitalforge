"""Pydantic schemas for strategy requests/responses."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.strategy import StrategyState, StrategyVersionSource

# --- Rule config schema (the shape of StrategyVersion.config_json) ---


class RuleCondition(BaseModel):
    """A single indicator-based condition, e.g. RSI(14) < 30."""

    model_config = ConfigDict(extra="forbid")

    indicator: Literal["RSI", "SMA", "EMA"]
    period: int = Field(gt=0)
    operator: Literal["less_than", "greater_than", "price_above", "price_below"]
    value: float | None = None  # not required for price_above/price_below


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
    model_config = ConfigDict(extra="forbid")

    stop_loss_pct: float | None = Field(default=None, gt=0)
    take_profit_pct: float | None = Field(default=None, gt=0)


class StrategyConfig(BaseModel):
    """The full structured shape of a strategy's rules, stored as
    StrategyVersion.config_json. schema_version allows this shape to
    evolve over time without requiring a database migration.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    symbol: str = Field(min_length=1, max_length=10)
    conditions: ConditionGroup
    position_sizing: PositionSizing
    exit: ExitRules


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