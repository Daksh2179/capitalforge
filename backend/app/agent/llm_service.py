"""LLMService: the interface every agent capability depends on.
GroqLLMClient (llm_client.py) is the only V1 implementation.
"""

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMService(ABC):
    @abstractmethod
    def generate_structured(
        self, messages: list[dict], response_model: type[T], schema_name: str
    ) -> T:
        raise NotImplementedError

    @abstractmethod
    def generate_text(self, messages: list[dict]) -> str:
        """Plain chat completion, no schema — for prose explanations
        where structured output would be the wrong tool."""
        raise NotImplementedError