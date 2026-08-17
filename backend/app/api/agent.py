"""Agent API: translation and confirmation endpoints.

/translate now runs the full 11-Agent ConversationPipeline instead of
TranslationService directly. The public request/response contract is
unchanged and fully backward-compatible with the existing frontend:

- BUILD/EDIT turns (StrategyBuilder/Editor ran) map to
  updated_draft/needs_clarification/needs_disambiguation/error exactly
  as before, using the real updated draft (see PipelineResult.draft)
  and applied_operations reconstructed from this turn's
  CapabilityResults.
- Every other turn (research/technical/portfolio/risk/fundamental/
  investment/education/performance) maps through the EXISTING
  "information" status, using ComposedResponse.text as
  information_message -- this is exactly how the current, unmodified
  frontend already renders a research-type answer as plain assistant
  text, so no frontend change is needed to see the new Agents working.
- agent_response is new and purely additive: ComposedResponse.text,
  always populated, regardless of turn type -- the forward-looking
  field a future Agent-native frontend should read directly, without
  needing to reverse-engineer meaning out of information_message once
  it starts carrying many different kinds of content.

A pipeline/LLM failure (e.g. Goal Extraction's Groq call failing) is
caught here and mapped to the same error-shaped response
TranslationService's own internal try/except already produces on its
failures -- so a failure looks and behaves the same regardless of
which path hit it, never an unhandled 500.
"""

import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agent.agent_contracts import AgentName, ResultKind
from app.agent.agents.educator_agent import EducatorAgent
from app.agent.agents.fundamental_analyst_agent import FundamentalAnalystAgent
from app.agent.agents.investment_analyst_agent import InvestmentAnalystAgent
from app.agent.agents.market_research_agent import MarketResearchAgent
from app.agent.agents.performance_analyst_agent import PerformanceAnalystAgent
from app.agent.agents.portfolio_analyst_agent import PortfolioAnalystAgent
from app.agent.agents.risk_advisor_agent import RiskAdvisorAgent
from app.agent.agents.strategy_builder_agent import StrategyBuilderAgent
from app.agent.agents.strategy_explainer_agent import StrategyExplainerAgent
from app.agent.agents.technical_analyst_agent import TechnicalAnalystAgent
from app.agent.context.fundamental_context import FinnhubClient, HttpxFinnhubClient
from app.agent.conversation_store import ConversationSession, ConversationStore
from app.agent.file_conversation_store import FileConversationStore
from app.agent.llm_client import LLMClient
from app.agent.llm_service import LLMService
from app.agent.pipeline.conversation_pipeline import ConversationPipeline, PipelineResult
from app.agent.pipeline.goal_extractor import GoalExtractor
from app.agent.pipeline.types import ConversationStepStatus
from app.agent.translation.translation_result import TranslationStatus
from app.agent.translation.translation_service import TranslationService
from app.agent.translation.validation import Severity, validate_strategy
from app.api.deps import get_db
from app.assets.asset_directory import AssetDirectory
from app.core.config import get_settings
from app.models.strategy import Strategy, StrategyState
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
from app.trading_engine.market_data.provider import MarketDataProvider

router = APIRouter(prefix="/agent", tags=["agent"])
_logger = logging.getLogger(__name__)

# --- Dependency providers ---
# Each is its own independently overridable FastAPI dependency
# (mirroring the pre-existing _get_translation_service pattern), so
# tests can fake exactly the pieces they need -- a real Groq/Alpaca/
# Finnhub call is never required for a test that doesn't explicitly
# want one.

def _get_llm_service() -> LLMService:
    settings = get_settings()
    return LLMClient(settings.groq_api_key, settings.groq_model)


def _get_market_data_provider() -> MarketDataProvider:
    settings = get_settings()
    return AlpacaMarketData(settings.alpaca_api_key, settings.alpaca_secret_key)


def _get_asset_directory() -> AssetDirectory:
    settings = get_settings()
    return AssetDirectory(settings.alpaca_api_key, settings.alpaca_secret_key)


def _get_finnhub_client() -> FinnhubClient | None:
    """None when no key is configured -- FundamentalAnalystAgent
    reports this honestly rather than the app failing to start."""
    settings = get_settings()
    if not settings.finnhub_api_key:
        return None
    return HttpxFinnhubClient(settings.finnhub_api_key)


def _get_translation_service(
    llm: LLMService = Depends(_get_llm_service),
    market_data: MarketDataProvider = Depends(_get_market_data_provider),
    asset_directory: AssetDirectory = Depends(_get_asset_directory),
) -> TranslationService:
    return TranslationService(llm, market_data, asset_directory)


def _get_goal_extractor(llm: LLMService = Depends(_get_llm_service)) -> GoalExtractor:
    return GoalExtractor(llm)


def _get_conversation_pipeline(
    db: Session = Depends(get_db),
    goal_extractor: GoalExtractor = Depends(_get_goal_extractor),
    asset_directory: AssetDirectory = Depends(_get_asset_directory),
    translation_service: TranslationService = Depends(_get_translation_service),
    market_data: MarketDataProvider = Depends(_get_market_data_provider),
    finnhub_client: FinnhubClient | None = Depends(_get_finnhub_client),
    llm: LLMService = Depends(_get_llm_service),
) -> ConversationPipeline:
    return ConversationPipeline(
        goal_extractor, asset_directory, StrategyBuilderAgent(translation_service),
        market_research_agent=MarketResearchAgent(market_data),
        technical_analyst_agent=TechnicalAnalystAgent(market_data),
        educator_agent=EducatorAgent(),
        strategy_explainer_agent=StrategyExplainerAgent(),
        portfolio_analyst_agent=PortfolioAnalystAgent(db),
        risk_advisor_agent=RiskAdvisorAgent(db, market_data),
        fundamental_analyst_agent=FundamentalAnalystAgent(finnhub_client),
        investment_analyst_agent=InvestmentAnalystAgent(llm),
        performance_analyst_agent=PerformanceAnalystAgent(db),
    )


def _get_conversation_store() -> ConversationStore:
    return FileConversationStore()


def _get_active_strategy(db: Session, user_id: uuid.UUID) -> Strategy | None:
    """The single query behind both draft-seeding (existing behavior)
    and strategy_id resolution (new) -- V1 supports exactly one active
    strategy per user."""
    strategies = strategy_service.list_strategies(db, user_id=user_id)
    return next((s for s in strategies if s.state != StrategyState.DRAFT), None)


def _load_active_strategy_config(db: Session, user_id: uuid.UUID) -> StrategyConfig | None:
    """A brand-new conversation always inherits the user's existing
    active strategy as its starting draft, since V1 supports exactly
    one active strategy at a time.

    A stale strategy predating a schema_version bump (see
    docs/decisions.md) will fail validation here -- rather than crash
    the whole request over one bad legacy row, this degrades to
    "no active strategy to seed from," same as if none existed. The
    real strategy/version row is untouched; only draft-seeding for
    this conversation is skipped.
    """
    active = _get_active_strategy(db, user_id)
    if active is None or active.current_version is None:
        return None
    try:
        return StrategyConfig.model_validate(active.current_version.config_json)
    except Exception:
        return None


def _build_translate_response(result: PipelineResult) -> TranslateResponse:
    """Maps PipelineResult onto the existing TranslateResponse contract.
    BUILD/EDIT turns get the exact same shape the frontend already
    renders (updated_draft/needs_clarification/needs_disambiguation/
    error). Every other turn maps through the pre-existing
    "information" bucket -- the current frontend already renders
    information_message as plain assistant text, so this requires no
    frontend change to expose everything the new Agents can do.
    agent_response is always populated, for the forward-looking,
    Agent-native frontend to consume directly later.
    """
    builder_step = next(
        (step for step in result.plan.steps
         if step.agent in (AgentName.STRATEGY_BUILDER, AgentName.STRATEGY_EDITOR)),
        None,
    )

    if builder_step is not None and builder_step.status == ConversationStepStatus.EXECUTED:
        errors = [r for r in builder_step.results if r.kind == ResultKind.ERROR]
        clarifications = [r.clarification for r in builder_step.results if r.clarification is not None]
        applied_operations = [r.draft_change for r in builder_step.results if r.draft_change is not None]

        if errors:
            message = errors[0].description
            return TranslateResponse(
                status=TranslationStatus.ERROR, error_message=message,
                agent_response=result.response.text or message,
            )

        if clarifications:
            clarification = clarifications[0]
            if clarification.candidates:
                return TranslateResponse(
                    status=TranslationStatus.NEEDS_DISAMBIGUATION,
                    disambiguation_message=clarification.question_text,
                    disambiguation_candidates=clarification.candidates,
                    agent_response=result.response.text or clarification.question_text,
                )
            return TranslateResponse(
                status=TranslationStatus.NEEDS_CLARIFICATION,
                clarification_message=clarification.question_text,
                agent_response=result.response.text or clarification.question_text,
            )

        if applied_operations:
            return TranslateResponse(
                status=TranslationStatus.UPDATED_DRAFT, draft=result.draft,
                applied_operations=applied_operations,
                agent_response=result.response.text or "; ".join(op.description for op in applied_operations),
            )

    message = result.response.text or "I'm not sure how to help with that yet."
    return TranslateResponse(status=TranslationStatus.INFORMATION, information_message=message, agent_response=message)


@router.post("/translate", response_model=TranslateResponse)
def translate(
    request: TranslateRequest,
    db: Session = Depends(get_db),
    pipeline: ConversationPipeline = Depends(_get_conversation_pipeline),
    store: ConversationStore = Depends(_get_conversation_store),
) -> TranslateResponse:
    session = store.get(request.conversation_id) or ConversationSession()

    if session.draft is None and not session.messages:
        session.draft = _load_active_strategy_config(db, request.user_id)

    active_strategy = _get_active_strategy(db, request.user_id)
    strategy_id = active_strategy.id if active_strategy is not None else None
    next_turn = session.turn_count + 1

    try:
        result = pipeline.handle_turn(
            request.message, session.messages, session.draft, session.memory, session.state,
            turn=next_turn, strategy_id=strategy_id, user_id=request.user_id,
        )
    except Exception:
        _logger.exception("Pipeline failure in /translate")
        # Never an unhandled 500 -- same failure shape TranslationService's
        # own internal try/except already produces on its own errors.
        assistant_content = "Something went wrong processing that."
        store.save(request.conversation_id, ConversationSession(
            messages=[
                *session.messages,
                {"role": "user", "content": request.message},
                {"role": "assistant", "content": assistant_content},
            ],
            draft=session.draft, state=session.state, memory=session.memory, turn_count=next_turn,
        ))
        return TranslateResponse(
            status=TranslationStatus.ERROR, error_message=assistant_content, agent_response=assistant_content,
        )

    response = _build_translate_response(result)

    store.save(request.conversation_id, ConversationSession(
        messages=[
            *session.messages,
            {"role": "user", "content": request.message},
            {"role": "assistant", "content": response.agent_response},
        ],
        draft=result.draft, state=result.state or session.state, memory=result.memory, turn_count=next_turn,
    ))

    return response


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
            db, strategy=strategy, config_json=session.draft.model_dump(mode="json"),
            source=StrategyVersionSource.CHAT, confirmed_now=True,
        )
    else:
        strategy = strategy_service.create_strategy(
            db, user_id=request.user_id, config_json=session.draft.model_dump(mode="json"),
            source=StrategyVersionSource.CHAT, confirmed_now=True,
        )

    strategy.state = StrategyState.ACTIVE
    db.commit()

    return ConfirmAcceptedResponse(strategy=StrategyResponse.model_validate(strategy), warnings=warnings)