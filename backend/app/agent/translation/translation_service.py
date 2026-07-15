"""TranslationService: orchestration only. Calls the LLM, routes each
resulting ParsedIntent through intent_translator + draft_updater, and
returns a TranslationResult. Does not persist conversation history —
that is the caller's responsibility (a higher-level conversation
service, not yet built).
"""

from app.agent.context.market_context import MarketContext, get_market_context
from app.agent.llm_service import LLMService
from app.agent.translation.draft_updater import AmbiguousAssetError, apply_fragment
from app.agent.translation.intent_translator import FragmentKind, translate_intent
from app.agent.translation.parsed_intent import IntentBatch
from app.agent.translation.prompts import TRANSLATION_SYSTEM_PROMPT
from app.agent.translation.translation_result import (
    AppliedOperation,
    TranslationResult,
    TranslationStatus,
)
from app.schemas.strategy import StrategyConfig
from app.trading_engine.market_data.provider import MarketDataProvider


class TranslationService:
    def __init__(self, llm_service: LLMService, market_data: MarketDataProvider) -> None:
        self._llm_service = llm_service
        self._market_data = market_data

    def translate(
        self, user_message: str, conversation_history: list[dict], draft: StrategyConfig | None
    ) -> TranslationResult:
        messages = [
            {"role": "system", "content": TRANSLATION_SYSTEM_PROMPT},
            *conversation_history,
            {"role": "user", "content": user_message},
        ]

        try:
            batch = self._llm_service.generate_structured(
                messages=messages, response_model=IntentBatch, schema_name="intent_batch"
            )
        except Exception as e:
            return TranslationResult(status=TranslationStatus.ERROR, error_message=str(e))

        current_draft = draft
        applied: list[AppliedOperation] = []

        for intent in batch.intents:
            fragment = translate_intent(intent)

            if fragment.kind == FragmentKind.CLARIFICATION_NEEDED:
                context = get_market_context(fragment.symbol, self._market_data) if fragment.symbol else None
                return TranslationResult(
                    status=TranslationStatus.NEEDS_CLARIFICATION,
                    draft=current_draft,
                    applied_operations=applied,
                    clarification_message=_build_clarification_message(fragment.clarification_context, context),
                )

            try:
                outcome = apply_fragment(current_draft, fragment)
            except AmbiguousAssetError as e:
                return TranslationResult(
                    status=TranslationStatus.NEEDS_DISAMBIGUATION,
                    draft=current_draft,
                    applied_operations=applied,
                    disambiguation_message="Which asset would you like to update?",
                    disambiguation_candidates=e.candidates,
                )

            current_draft = outcome.config
            applied.append(AppliedOperation(
                operation=fragment.kind.value, symbol=fragment.symbol, description=outcome.description
            ))

        return TranslationResult(
            status=TranslationStatus.UPDATED_DRAFT, draft=current_draft, applied_operations=applied
        )


def _build_clarification_message(context_text: str | None, market: MarketContext | None) -> str:
    parts = []
    if market is not None:
        parts.append(
            f"{market.symbol} is currently trading around ${market.current_price:.2f}. "
            f"Its 52-week range is ${market.week_52_low:.2f}-${market.week_52_high:.2f}."
        )
    if context_text:
        parts.append(context_text)
    parts.append("What price or price range would you consider?")
    return " ".join(parts)