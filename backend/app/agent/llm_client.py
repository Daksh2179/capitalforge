"""LLMClient: thin wrapper around Groq's structured-output API.

Every response is validated against a caller-provided Pydantic model
via Groq's native strict-mode JSON Schema support — never manual JSON
parsing with best-effort hope. If the model can't produce schema-
compliant output, this raises rather than returning a guess.
"""

import json
from typing import Any, TypeVar

from groq import Groq
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMClient:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = Groq(api_key=api_key)
        self._model = model

    def generate_structured(
        self, messages: list[dict], response_model: type[T], schema_name: str
    ) -> T:
        """messages follows the standard {"role", "content"} chat shape."""
        schema = _make_strict_compatible(response_model.model_json_schema())

        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,  # type: ignore[call-overload]
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


def _make_strict_compatible(schema: dict[str, Any]) -> dict[str, Any]:
    """Recursively add additionalProperties: false to every object in
    the schema. Groq's strict mode requires this on every object,
    including nested ones, but Pydantic's model_json_schema() doesn't
    set it by default. Also descends into $defs, since Pydantic
    represents nested models as $ref pointers into $defs rather than
    inlining them.
    """
    if schema.get("type") == "object" and "additionalProperties" not in schema:
        schema["additionalProperties"] = False

    for key in ("properties", "$defs"):
        if key in schema:
            for value in schema[key].values():
                if isinstance(value, dict):
                    _make_strict_compatible(value)

    if "items" in schema and isinstance(schema["items"], dict):
        _make_strict_compatible(schema["items"])

    return schema