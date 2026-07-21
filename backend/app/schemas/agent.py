"""Request/response schemas for the agent API: translation and confirmation."""

import uuid

from pydantic import BaseModel, ConfigDict

from app.agent.translation.translation_result import AppliedOperation, TranslationStatus
from app.agent.translation.validation import ValidationIssue
from app.schemas.strategy import StrategyConfig, StrategyResponse


class TranslateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    user_id: uuid.UUID
    message: str


class TranslateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: TranslationStatus
    draft: StrategyConfig | None = None
    applied_operations: list[AppliedOperation] = []
    clarification_message: str | None = None
    disambiguation_message: str | None = None
    disambiguation_candidates: list[str] = []
    error_message: str | None = None
    information_message: str | None = None


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    conversation_id: str
    strategy_id: uuid.UUID | None = None


class ConfirmRejectedResponse(BaseModel):
    """Returned (not raised as an error) when validation finds blocking
    issues — nothing was persisted, this is the caller's chance to fix
    the draft and try again."""

    model_config = ConfigDict(extra="forbid")

    confirmed: bool = False
    issues: list[ValidationIssue]


class ConfirmAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: bool = True
    strategy: StrategyResponse
    warnings: list[ValidationIssue] = []
    
class ConversationSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[dict]
    draft: StrategyConfig | None = None