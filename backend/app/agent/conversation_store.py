"""ConversationStore: the interface every conversation persistence
implementation adheres to. FileConversationStore (local JSON) is the
only V1 implementation — swappable for a database-backed store later
without touching any agent logic that depends on this interface.

Stores a ConversationSession per conversation_id: the message history
plus the current working draft, since restoring "the conversation" on
reload means restoring both, not just the transcript.
"""

from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.schemas.strategy import StrategyConfig
from app.agent.conversation_state import ConversationState

class ConversationSession(BaseModel):
    messages: list[dict] = []
    draft: StrategyConfig | None = None
    state: ConversationState = ConversationState()


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