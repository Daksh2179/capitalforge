"""Agent API: translation and confirmation endpoints. Thin routers —
all real logic lives in TranslationService, validate_strategy,
strategy_service, and ConversationStore.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agent.conversation_store import ConversationSession, ConversationStore
from app.agent.file_conversation_store import FileConversationStore
from app.agent.llm_client import LLMClient
from app.agent.translation.translation_result import TranslationResult
from app.agent.translation.translation_service import TranslationService
from app.agent.translation.validation import Severity, validate_strategy
from app.api.deps import get_db
from app.assets.asset_directory import AssetDirectory
from app.core.config import get_settings
from app.models.strategy import StrategyState
from app.schemas.agent import (
    ConfirmAcceptedResponse,
    ConfirmRejectedResponse,
    ConfirmRequest,
    ConversationSessionResponse,
    TranslateRequest,
    TranslateResponse,
)
from app.schemas.strategy import StrategyConfig, StrategyResponse, StrategyVersionSource
from app.services import strategy_service
from app.trading_engine.market_data.alpaca_market_data import AlpacaMarketData

router = APIRouter(prefix="/agent", tags=["agent"])


def _get_translation_service() -> TranslationService:
    settings = get_settings()
    llm = LLMClient(settings.groq_api_key, settings.groq_model)
    market_data = AlpacaMarketData(settings.alpaca_api_key, settings.alpaca_secret_key)
    asset_directory = AssetDirectory(settings.alpaca_api_key, settings.alpaca_secret_key)
    return TranslationService(llm, market_data, asset_directory)


def _get_conversation_store() -> ConversationStore:
    return FileConversationStore()


def _load_active_strategy_config(db: Session, user_id: uuid.UUID) -> StrategyConfig | None:
    """A brand-new conversation always inherits the user's existing
    active strategy as its starting draft, since V1 supports exactly
    one active strategy at a time. There is currently no way to start
    a conversation "clean" except by explicitly asking the agent to
    remove all rules first — this is a deliberate choice, not an
    oversight, matching the single-active-strategy constraint used
    throughout the rest of the app.
    """
    strategies = strategy_service.list_strategies(db, user_id=user_id)
    active = next((s for s in strategies if s.state != StrategyState.DRAFT), None)
    if active is None or active.current_version is None:
        return None
    return StrategyConfig.model_validate(active.current_version.config_json)


@router.post("/translate", response_model=TranslateResponse)
def translate(
    request: TranslateRequest,
    db: Session = Depends(get_db),
    service: TranslationService = Depends(_get_translation_service),
    store: ConversationStore = Depends(_get_conversation_store),
) -> TranslateResponse:
    session = store.get(request.conversation_id) or ConversationSession()

    if session.draft is None and not session.messages:
        session.draft = _load_active_strategy_config(db, request.user_id)

    result, new_state = service.translate(
        request.message, session.messages, session.draft, session.state
    )

    assistant_content = _summarize_result_for_history(result)
    updated_session = ConversationSession(
        messages=[
            *session.messages,
            {"role": "user", "content": request.message},
            {"role": "assistant", "content": assistant_content},
        ],
        draft=result.draft,
        state=new_state,
    )
    store.save(request.conversation_id, updated_session)

    return TranslateResponse(**result.model_dump())


@router.get("/conversations/{conversation_id}", response_model=ConversationSessionResponse)
def get_conversation_session(
    conversation_id: str,
    store: ConversationStore = Depends(_get_conversation_store),
) -> ConversationSessionResponse:
    session = store.get(conversation_id) or ConversationSession()
    return ConversationSessionResponse(messages=session.messages, draft=session.draft)


@router.post("/confirm", response_model=ConfirmAcceptedResponse | ConfirmRejectedResponse)
def confirm(
    request: ConfirmRequest,
    db: Session = Depends(get_db),
    store: ConversationStore = Depends(_get_conversation_store),
) -> ConfirmAcceptedResponse | ConfirmRejectedResponse:
    session = store.get(request.conversation_id)
    if session is None or session.draft is None:
        raise HTTPException(status_code=400, detail="No draft to confirm for this conversation")

    issues = validate_strategy(session.draft)
    blocking = [i for i in issues if i.severity == Severity.ERROR]

    if blocking:
        return ConfirmRejectedResponse(issues=issues)

    warnings = [i for i in issues if i.severity == Severity.WARNING]

    if request.strategy_id is not None:
        strategy = strategy_service.get_strategy(db, strategy_id=request.strategy_id)
        if strategy is None:
            raise HTTPException(status_code=404, detail="Strategy not found")
        strategy_service.create_new_version(
            db, strategy=strategy, config_json=session.draft.model_dump(),
            source=StrategyVersionSource.CHAT, confirmed_now=True,
        )
    else:
        strategy = strategy_service.create_strategy(
            db, user_id=request.user_id, config_json=session.draft.model_dump(),
            source=StrategyVersionSource.CHAT, confirmed_now=True,
        )

    strategy.state = StrategyState.ACTIVE
    db.commit()

    return ConfirmAcceptedResponse(strategy=StrategyResponse.model_validate(strategy), warnings=warnings)


def _summarize_result_for_history(result: TranslationResult) -> str:
    """What the assistant 'said', for the next turn's context — plain
    text only, never the structured TranslationResult itself."""
    if result.status.value == "updated_draft":
        if result.applied_operations:
            return "; ".join(op.description for op in result.applied_operations)
        return "Understood."
    if result.status.value == "needs_clarification":
        return result.clarification_message or "Could you clarify that?"
    if result.status.value == "needs_disambiguation":
        return result.disambiguation_message or "Which asset did you mean?"
    return result.error_message or "Something went wrong processing that."