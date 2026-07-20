"""TranslationService: orchestration only. Calls the LLM, routes each
resulting ParsedIntent through intent_translator + draft_updater, and
returns a TranslationResult plus an updated ConversationState. State
updates are derived deterministically from what actually happened —
never from LLM self-reporting.
"""

from app.agent.context.market_context import MarketContext, get_market_context
from app.agent.conversation_state import ConversationState, PendingClarification
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
from app.assets.asset_directory import AssetDirectory
from app.schemas.strategy import StrategyConfig
from app.trading_engine.market_data.provider import MarketDataProvider


class TranslationService:
    def __init__(
        self, llm_service: LLMService, market_data: MarketDataProvider, asset_directory: AssetDirectory
    ) -> None:
        self._llm_service = llm_service
        self._market_data = market_data
        self._asset_directory = asset_directory

    def translate(
        self,
        user_message: str,
        conversation_history: list[dict],
        draft: StrategyConfig | None,
        state: ConversationState | None = None,
    ) -> tuple[TranslationResult, ConversationState]:
        state = state or ConversationState()

        messages = [
            {"role": "system", "content": TRANSLATION_SYSTEM_PROMPT},
            {"role": "system", "content": _render_state_context(state)},
            *conversation_history,
            {"role": "user", "content": user_message},
        ]

        try:
            batch = self._llm_service.generate_structured(
                messages=messages, response_model=IntentBatch, schema_name="intent_batch"
            )
        except Exception as e:
            return TranslationResult(status=TranslationStatus.ERROR, error_message=str(e)), state

        for intent in batch.intents:
            if intent.symbol is not None:
                resolved = self._resolve_symbol(intent.symbol)
                if resolved is None:
                    return TranslationResult(
                        status=TranslationStatus.ERROR,
                        error_message=f"Couldn't recognize '{intent.symbol}' as a valid stock or ETF symbol.",
                    ), state
                intent.symbol = resolved

        current_draft = draft
        applied: list[AppliedOperation] = []
        new_state = state.model_copy(deep=True)

        for intent in batch.intents:
            fragment = translate_intent(intent)

            if fragment.kind == FragmentKind.CLARIFICATION_NEEDED:
                context = get_market_context(fragment.symbol, self._market_data) if fragment.symbol else None
                new_state.pending_clarification = PendingClarification(
                    about_symbol=fragment.symbol,
                    question_text=fragment.clarification_context or "Could you clarify that?",
                )
                result = TranslationResult(
                    status=TranslationStatus.NEEDS_CLARIFICATION,
                    draft=current_draft,
                    applied_operations=applied,
                    clarification_message=_build_clarification_message(fragment.clarification_context, context),
                )
                return result, new_state

            try:
                outcome = apply_fragment(current_draft, fragment)
            except AmbiguousAssetError as e:
                new_state.pending_clarification = PendingClarification(
                    field=fragment.kind.value,
                    question_text="Which asset would you like to update?",
                )
                result = TranslationResult(
                    status=TranslationStatus.NEEDS_DISAMBIGUATION,
                    draft=current_draft,
                    applied_operations=applied,
                    disambiguation_message="Which asset would you like to update?",
                    disambiguation_candidates=e.candidates,
                )
                return result, new_state

            current_draft = outcome.config
            applied.append(AppliedOperation(
                operation=fragment.kind.value, symbol=fragment.symbol, description=outcome.description
            ))

            # Deterministic state update: derived from what actually
            # happened this turn, never from the LLM's own report.
            new_state.pending_clarification = None
            if fragment.symbol:
                new_state.focused_symbol = fragment.symbol
                if fragment.symbol not in new_state.recently_referenced_symbols:
                    new_state.recently_referenced_symbols = (
                        [fragment.symbol] + new_state.recently_referenced_symbols
                    )[:5]
            new_state.last_modified_field = fragment.kind.value
            new_state.last_successful_operation = outcome.description

        result = TranslationResult(
            status=TranslationStatus.UPDATED_DRAFT, draft=current_draft, applied_operations=applied
        )
        return result, new_state

    def _resolve_symbol(self, raw_symbol: str) -> str | None:
        """Resolves a company name or ticker (in any capitalization,
        e.g. "Apple", "appl", "nextera") to a real, tradable ticker
        symbol, using the same AssetDirectory search already verified
        correct for this exact purpose. Returns None if nothing
        matches — callers must not silently pass through an
        unresolved symbol.
        """
        matches = self._asset_directory.search(raw_symbol, limit=1)
        if not matches:
            return None
        return matches[0].symbol


def _render_state_context(state: ConversationState) -> str:
    """Serializes ConversationState into a short, plain-text block the
    LLM can use to resolve follow-up references. Not chat history —
    a structured fact sheet of what's currently in focus."""
    parts = ["Current conversation state:"]
    if state.focused_symbol:
        parts.append(f"- Currently discussing: {state.focused_symbol}")
    if state.last_modified_field:
        parts.append(f"- Last changed: {state.last_modified_field}")
    if state.pending_clarification:
        parts.append(f"- Open question: {state.pending_clarification.question_text}")
    if state.recently_referenced_symbols:
        parts.append(f"- Recently discussed: {', '.join(state.recently_referenced_symbols)}")
    if len(parts) == 1:
        parts.append("- Nothing discussed yet this conversation.")
    return "\n".join(parts)


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