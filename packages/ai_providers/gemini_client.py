from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from packages.ai_providers.base import (
    CompletionRequest,
    CompletionResponse,
    LLMClient,
)

DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiClient(LLMClient):
    def __init__(self, api_key: str, model: str | None = None) -> None:
        self._client = genai.Client(api_key=api_key)
        self._default_model = model or DEFAULT_MODEL

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        contents: list[dict[str, Any]] = []
        for m in request.messages:
            role = "user" if m.role == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m.content}]})

        config = types.GenerateContentConfig(
            system_instruction=request.system,
            temperature=request.temperature,
            max_output_tokens=request.max_tokens,
        )
        result = self._client.models.generate_content(
            model=request.model or self._default_model,
            contents=contents,
            config=config,
        )
        text = result.text or ""
        raw = result.model_dump() if hasattr(result, "model_dump") else {}
        usage = raw.get("usage_metadata") or {}
        return CompletionResponse(
            content=text,
            raw=raw,
            input_tokens=usage.get("prompt_token_count", 0),
            output_tokens=usage.get("candidates_token_count", 0),
        )

    def validate_key(self) -> bool:
        try:
            self._client.models.generate_content(
                model=self._default_model,
                contents="ping",
                config=types.GenerateContentConfig(max_output_tokens=1),
            )
        except genai_errors.ClientError as exc:
            if getattr(exc, "code", None) in (401, 403):
                return False
            raise
        return True
