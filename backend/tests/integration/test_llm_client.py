"""Integration test for LLMClient, run against the real Groq API.
Requires a valid GROQ_API_KEY in .env.
"""

from pydantic import BaseModel

from app.agent.llm_client import LLMClient
from app.core.config import get_settings


class _SimpleExtraction(BaseModel):
    """Deliberately strict-mode-compliant: every field required,
    no Optional. Used only to verify the client/API work — not related
    to any real domain schema."""

    animal_mentioned: str
    is_friendly: bool


def _client() -> LLMClient:
    settings = get_settings()
    return LLMClient(settings.groq_api_key, settings.groq_model)


def test_generate_structured_returns_valid_typed_response():
    client = _client()

    result = client.generate_structured(
        messages=[
            {"role": "system", "content": "Extract the animal mentioned and whether it sounds friendly."},
            {"role": "user", "content": "My dog Max is the sweetest, most gentle golden retriever."},
        ],
        response_model=_SimpleExtraction,
        schema_name="simple_extraction",
    )

    assert isinstance(result, _SimpleExtraction)
    assert "dog" in result.animal_mentioned.lower() or "retriever" in result.animal_mentioned.lower()
    assert result.is_friendly is True


def test_generate_structured_reflects_negative_case():
    client = _client()

    result = client.generate_structured(
        messages=[
            {"role": "system", "content": "Extract the animal mentioned and whether it sounds friendly."},
            {"role": "user", "content": "That wasp chased me around the yard and stung my arm twice."},
        ],
        response_model=_SimpleExtraction,
        schema_name="simple_extraction",
    )

    assert isinstance(result, _SimpleExtraction)
    assert "wasp" in result.animal_mentioned.lower()
    assert result.is_friendly is False