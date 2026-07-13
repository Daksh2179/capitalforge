"""ConversationStore: the interface every conversation persistence
implementation adheres to. FileConversationStore (local JSON) is the
only V1 implementation — swappable for a database-backed store later
without touching any agent logic that depends on this interface.
"""

from abc import ABC, abstractmethod


class ConversationStore(ABC):
    @abstractmethod
    def get(self, conversation_id: str) -> list[dict] | None:
        """Return the stored message list for a conversation, or None
        if no conversation with this id exists yet."""
        raise NotImplementedError

    @abstractmethod
    def save(self, conversation_id: str, messages: list[dict]) -> None:
        """Persist the full message list for a conversation, replacing
        whatever was previously stored under this id."""
        raise NotImplementedError