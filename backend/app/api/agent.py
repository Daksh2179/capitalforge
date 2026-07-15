"""Agent API: translation and confirmation endpoints. Thin routers —
all real logic lives in TranslationService, validate_strategy, and
strategy_service, exactly per the module design used everywhere else.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agent.llm_client import LLMClient
from app.agent.translation.translation_service import TranslationService
from app.agent.translation.validation import Severity, validate_strategy
from app.api.deps import get_db
from app.core.config import get_settings
from app.schemas.agent import (
    ConfirmAcceptedResponse,
    ConfirmRejectedResponse,
    ConfirmRequest,
    TranslateRequest,
    TranslateResponse,
)
from app.schemas.strategy import StrategyResponse, StrategyVersionSource
from app.services import strategy_service
from app.trading_engine.market_data.alpaca_market_data import AlpacaMarketData

router = APIRouter(prefix="/agent", tags=["agent"])


def _get_translation_service() -> TranslationService:
    settings = get_settings()
    llm = LLMClient(settings.groq_api_key, settings.groq_model)
    market_data = AlpacaMarketData(settings.alpaca_api_key, settings.alpaca_secret_key)
    return TranslationService(llm, market_data)


@router.post("/translate", response_model=TranslateResponse)
def translate(
    request: TranslateRequest,
    service: TranslationService = Depends(_get_translation_service),
) -> TranslateResponse:
    result = service.translate(request.message, request.conversation_history, request.draft)
    return TranslateResponse(**result.model_dump())


@router.post("/confirm", response_model=ConfirmAcceptedResponse | ConfirmRejectedResponse)
def confirm(
    request: ConfirmRequest,
    db: Session = Depends(get_db),
) -> ConfirmAcceptedResponse | ConfirmRejectedResponse:
    issues = validate_strategy(request.draft)
    blocking = [i for i in issues if i.severity == Severity.ERROR]

    if blocking:
        return ConfirmRejectedResponse(issues=issues)

    warnings = [i for i in issues if i.severity == Severity.WARNING]

    if request.strategy_id is not None:
        strategy = strategy_service.get_strategy(db, strategy_id=request.strategy_id)
        if strategy is None:
            raise HTTPException(status_code=404, detail="Strategy not found")
        strategy_service.create_new_version(
            db, strategy=strategy, config_json=request.draft.model_dump(),
            source=StrategyVersionSource.CHAT, confirmed_now=True,
        )
    else:
        strategy = strategy_service.create_strategy(
            db, user_id=request.user_id, config_json=request.draft.model_dump(),
            source=StrategyVersionSource.CHAT, confirmed_now=True,
        )

    return ConfirmAcceptedResponse(strategy=StrategyResponse.model_validate(strategy), warnings=warnings)