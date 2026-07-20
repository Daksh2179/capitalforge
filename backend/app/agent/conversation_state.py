"""ConversationState: the AI's working memory for one conversation —
what the assistant currently knows, distinct from chat history (what
was said). Deterministically owned and updated by TranslationService,
based on what actually happened each turn — never self-reported by
the LLM. Designed to grow: new fields slot in here, not onto
ConversationSession directly.
"""

from pydantic import BaseModel, ConfigDict


class PendingClarification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    about_symbol: str | None = None
    field: str | None = None
    question_text: str


class ConversationState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    focused_symbol: str | None = None
    last_modified_field: str | None = None
    last_successful_operation: str | None = None
    pending_clarification: PendingClarification | None = None
    recently_referenced_symbols: list[str] = []