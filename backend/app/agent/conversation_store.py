"""ConversationStore: the interface every conversation persistence
implementation adheres to. FileConversationStore (local JSON) is the
only V1 implementation — swappable for a database-backed store later
without touching any agent logic that depends on this interface.

Stores a ConversationSession per conversation_id: message history, the
current working draft, ConversationState (TranslationService's legacy
working memory, permanent), ConversationMemory (the pipeline's Agent-
facing memory), and turn_count (incremented once per /translate call,
threaded into ConversationPipeline.handle_turn's turn parameter).

memory and turn_count are additive widenings of this type, same as
draft was added once before (per docs/decisions.md) -- both are
trivially JSON-serializable via the exact same model_dump_json/
model_validate_json mechanism already used for state.
"""

from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.agent.conversation_memory import ConversationMemory
from app.agent.conversation_state import ConversationState
from app.schemas.strategy import StrategyConfig


class ConversationSession(BaseModel):
    messages: list[dict] = []
    draft: StrategyConfig | None = None
    state: ConversationState = ConversationState()
    memory: ConversationMemory = ConversationMemory()
    turn_count: int = 0


class ConversationStore(ABC):
    @abstractmethod
    def get(self, conversation_id: str) -> ConversationSession | None:
        """Return the stored session for a conversation, or None if no
        conversation with this id exists yet."""
        raise NotImplementedError

    @abstractmethod
    def save(self, conversation_id: str, session: ConversationSession) -> None:
        """Persist the full session for a conversation, replacing
        whatever was previously stored under this id."""
        raise NotImplementedError