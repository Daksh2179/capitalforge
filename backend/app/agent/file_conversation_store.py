"""FileConversationStore: local JSON file persistence, one file per
conversation. Gitignored — this is per-machine runtime state, not
something that belongs in version control.
"""

import re
from pathlib import Path

from app.agent.conversation_store import ConversationSession, ConversationStore


class FileConversationStore(ConversationStore):
    """The only V1 implementation of ConversationStore."""

    def __init__(self, directory: str | Path = "conversations") -> None:
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)

    def get(self, conversation_id: str) -> ConversationSession | None:
        path = self._path_for(conversation_id)
        if not path.exists():
            return None
        return ConversationSession.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, conversation_id: str, session: ConversationSession) -> None:
        path = self._path_for(conversation_id)
        path.write_text(session.model_dump_json(indent=2), encoding="utf-8")

    def _path_for(self, conversation_id: str) -> Path:
        safe_id = self._sanitize(conversation_id)
        return self._directory / f"{safe_id}.json"

    @staticmethod
    def _sanitize(conversation_id: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", conversation_id):
            raise ValueError(
                f"Invalid conversation_id: {conversation_id!r}. "
                f"Only alphanumeric characters, hyphens, and underscores are allowed."
            )
        return conversation_id