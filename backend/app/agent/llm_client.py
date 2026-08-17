"""LLMClient: thin wrapper around Groq's structured-output API.
Implements LLMService — the only file permitted to import from groq.

Every response is validated against a caller-provided Pydantic model
via Groq's native strict-mode JSON Schema support — never manual JSON
parsing with best-effort hope.
"""

import json
from typing import Any, TypeVar

from groq import Groq
from pydantic import BaseModel

from app.agent.llm_service import LLMService

T = TypeVar("T", bound=BaseModel)
_MAX_TOKENS = 2048
# Groq's tokens-per-minute limit for this model/tier counts the
# *requested* max_tokens reservation itself, not actual usage --
# confirmed by hitting a real 413 with max_tokens=8192 alone (before
# any prompt content), against a documented account ceiling of 8000
# TPM. 2048 leaves ~6000 tokens of real headroom for prompt content
# (system prompt + conversation history + memory context) while still
# being well above whatever Groq's undocumented default was, which was
# too small to let a reasoning-style model finish a nontrivial
# extraction (the original failure this whole fix exists for).

class LLMClient(LLMService):
    def __init__(self, api_key: str, model: str) -> None:
        self._client = Groq(api_key=api_key)
        self._model = model

    def generate_structured(
        self, messages: list[dict], response_model: type[T], schema_name: str
    ) -> T:
        schema = _make_strict_compatible(response_model.model_json_schema())

        last_error: Exception | None = None
        for attempt in range(2):  # one retry -- structured-output generation
                                    # occasionally produces invalid JSON on a
                                    # given attempt even with a good prompt;
                                    # this is inherent to the approach, not
                                    # something a better prompt eliminates.
            try:
                response = self._client.chat.completions.create(  # type: ignore[call-overload]
                    model=self._model,
                    messages=messages,
                    max_tokens=_MAX_TOKENS,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": schema_name,
                            "strict": True,
                            "schema": schema,
                        },
                    },
                )
                content = response.choices[0].message.content
                if content is None:
                    raise ValueError("Groq returned an empty response with no content")
                return response_model.model_validate(json.loads(content))
            except Exception as e:
                last_error = e
                continue

        assert last_error is not None
        raise last_error

    def generate_text(self, messages: list[dict]) -> str:
        response = self._client.chat.completions.create(
            model=self._model, messages=messages, max_tokens=_MAX_TOKENS,  # type: ignore[call-overload, arg-type]
        )
        content = response.choices[0].message.content
        if content is None:
            raise ValueError("Groq returned an empty response with no content")
        return content


def _make_strict_compatible(schema: dict[str, Any]) -> dict[str, Any]:
    """Recursively force every object to additionalProperties: false
    and every property into `required` (optionality expressed only via
    a null-inclusive type/anyOf, which Pydantic's Optional already
    produces). Groq's strict mode requires both; Pydantic's
    model_json_schema() sets neither by default. Descends into
    properties, $defs, items, and anyOf branches, since Pydantic
    represents nested/optional models across all of these.
    """
    if "properties" in schema:
        schema["additionalProperties"] = False
        schema["required"] = list(schema["properties"].keys())
        for value in schema["properties"].values():
            if isinstance(value, dict):
                _make_strict_compatible(value)

    if "$defs" in schema:
        for value in schema["$defs"].values():
            _make_strict_compatible(value)

    if "items" in schema and isinstance(schema["items"], dict):
        _make_strict_compatible(schema["items"])

    if "anyOf" in schema:
        for branch in schema["anyOf"]:
            if isinstance(branch, dict):
                _make_strict_compatible(branch)

    return schema