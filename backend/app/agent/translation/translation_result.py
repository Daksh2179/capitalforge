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
    changed without diffing two StrategyConfig objects.

    reasoning is None whenever the user supplied the value directly --
    never fabricated. Currently the only non-None case is a brand-new
    rule's capital_allocation defaulting to 5% because none was
    specified (see draft_updater.py). StrategyExplainerAgent reads
    this field to answer "why" questions honestly.
    """

    model_config = ConfigDict(extra="forbid")

    operation: str
    symbol: str | None = None
    description: str
    reasoning: str | None = None

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