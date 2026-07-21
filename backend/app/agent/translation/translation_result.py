"""TranslationResult: what TranslationService returns for one turn.
status determines which payload field is meaningful — never a soup of
nullable fields where callers must infer state from which ones are set.
"""

import enum

from pydantic import BaseModel, ConfigDict

from app.schemas.strategy import StrategyConfig


class TranslationStatus(str, enum.Enum):
    UPDATED_DRAFT = "updated_draft"
    NEEDS_CLARIFICATION = "needs_clarification"
    NEEDS_DISAMBIGUATION = "needs_disambiguation"
    INFORMATION = "information"
    ERROR = "error"


class AppliedOperation(BaseModel):
    """One human-readable summary of a single change applied to the
    draft, so downstream consumers (frontend, logs) can show what
    changed without diffing two StrategyConfig objects."""

    model_config = ConfigDict(extra="forbid")

    operation: str
    symbol: str | None = None
    description: str


class TranslationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: TranslationStatus

    draft: StrategyConfig | None = None
    applied_operations: list[AppliedOperation] = []

    clarification_message: str | None = None
    disambiguation_message: str | None = None
    disambiguation_candidates: list[str] = []
    
    information_message: str | None = None

    error_message: str | None = None