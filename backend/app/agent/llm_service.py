"""LLMService: the interface TranslationService and other agent
capabilities depend on. GroqLLMClient (llm_client.py) is the only V1
implementation — swappable for another provider without touching
anything that calls generate_structured.
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