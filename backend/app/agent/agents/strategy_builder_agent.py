"""StrategyBuilderAgent: a thin adapter over the existing
TranslationService, wrapped in the new Agent contract shape. This is
the first Agent implementation. It changes NO existing behavior --
TranslationService is untouched, and this class is not yet wired into
api/agent.py or any live route.

Deliberately still speaks ConversationState (not ConversationMemory)
to TranslationService directly, and takes raw inputs rather than a
GroundedContext -- GroundedContext has no producer yet (Goal
Extraction/Grounding don't exist as code). This is a known, planned,
temporary seam, revisited in step 4, not an oversight.

See docs/decisions.md for two real mismatches found while mapping
TranslationResult -> CapabilityResult: applied_operations is a list
while CapabilityResult.draft_change is singular (resolved by returning
list[CapabilityResult], one per operation, not by cramming several
edits into one blob); and disambiguation_candidates had nowhere to go
in ClarificationRequest until candidates was added to it.
"""

from app.agent.agent_contracts import AgentName, CapabilityResult, ClarificationRequest
from app.agent.conversation_memory import EntityReference
from app.agent.conversation_state import ConversationState
from app.agent.translation.translation_result import TranslationResult, TranslationStatus
from app.agent.translation.translation_service import TranslationService
from app.schemas.strategy import StrategyConfig


class StrategyBuilderAgent:
    name = AgentName.STRATEGY_BUILDER

    def __init__(self, translation_service: TranslationService) -> None:
        self._translation_service = translation_service

    def execute(
        self,
        user_message: str,
        conversation_history: list[dict],
        draft: StrategyConfig | None,
        state: ConversationState | None,
    ) -> tuple[list[CapabilityResult], ConversationState, TranslationResult]:
        """Returns (capability_results, new_conversation_state,
        raw_translation_result). raw_translation_result is returned
        alongside the new-architecture results because api/agent.py's
        current /translate route depends on the exact TranslationResult
        shape (TranslateResponse serializes it directly) -- this step
        must not change that. Once step 4 retires the old response
        shape, this third return value goes away.
        """
        result, new_state = self._translation_service.translate(
            user_message, conversation_history, draft, state
        )
        return self._to_capability_results(result), new_state, result

    def _to_capability_results(self, result: TranslationResult) -> list[CapabilityResult]:
        if result.status == TranslationStatus.UPDATED_DRAFT:
            if not result.applied_operations:
                return [CapabilityResult(agent=self.name, description="Understood.")]
            return [
                CapabilityResult(
                    agent=self.name,
                    description=op.description,
                    reasoning=None,  # draft_updater records WHAT changed, never WHY --
                                      # never fabricated here. Strategy Explainer's job later.
                    draft_change=op,
                    affected_entities=(
                        [EntityReference(kind="symbol", value=op.symbol, display_name=op.symbol)]
                        if op.symbol else []
                    ),
                )
                for op in result.applied_operations
            ]

        if result.status == TranslationStatus.NEEDS_CLARIFICATION:
            message = result.clarification_message or "Could you clarify that?"
            return [CapabilityResult(
                agent=self.name, description=message,
                clarification=ClarificationRequest(question_text=message),
                # about=None deliberately: TranslationResult doesn't expose
                # which symbol (if any) a clarification concerns at this
                # layer -- not guessed here.
            )]

        if result.status == TranslationStatus.NEEDS_DISAMBIGUATION:
            message = result.disambiguation_message or "Which asset did you mean?"
            return [CapabilityResult(
                agent=self.name, description=message,
                clarification=ClarificationRequest(
                    question_text=message, candidates=result.disambiguation_candidates,
                ),
            )]

        if result.status == TranslationStatus.INFORMATION:
            message = result.information_message or "Here's what I found."
            return [CapabilityResult(agent=self.name, description=message, facts=[message])]

        # ERROR
        message = result.error_message or "Something went wrong processing that."
        return [CapabilityResult(agent=self.name, description=message)]