"""FileConversationStore: local JSON file persistence, one file per
conversation. Gitignored — this is per-machine runtime state, not
something that belongs in version control. Exists specifically so a
fresh clone of the repo runs immediately with zero extra infrastructure.
"""

import json
import re
from pathlib import Path


class FileConversationStore:
    """Implements ConversationStore. Not declared as a formal subclass
    (see note in tests) to keep this file free of any import beyond
    the standard library — the interface contract is enforced by
    tests and by mypy structural typing, not inheritance.
    """

    def __init__(self, directory: str | Path = "conversations") -> None:
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)

    def get(self, conversation_id: str) -> list[dict] | None:
        path = self._path_for(conversation_id)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def save(self, conversation_id: str, messages: list[dict]) -> None:
        path = self._path_for(conversation_id)
        with path.open("w", encoding="utf-8") as f:
            json.dump(messages, f, indent=2)

    def _path_for(self, conversation_id: str) -> Path:
        safe_id = self._sanitize(conversation_id)
        return self._directory / f"{safe_id}.json"

    @staticmethod
    def _sanitize(conversation_id: str) -> str:
        """Reject or strip anything that isn't a safe filename
        component, to prevent path traversal via a crafted
        conversation_id (e.g. '../../etc/passwd')."""
        if not re.fullmatch(r"[A-Za-z0-9_-]+", conversation_id):
            raise ValueError(
                f"Invalid conversation_id: {conversation_id!r}. "
                f"Only alphanumeric characters, hyphens, and underscores are allowed."
            )
        return conversation_id