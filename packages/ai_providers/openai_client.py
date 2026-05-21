from typing import Any

from openai import AuthenticationError, OpenAI

from packages.ai_providers.base import (
    CompletionRequest,
    CompletionResponse,
    LLMClient,
)

DEFAULT_MODEL = "gpt-4o"


class OpenAIClient(LLMClient):
    def __init__(self, api_key: str, model: str | None = None) -> None:
        self._client = OpenAI(api_key=api_key)
        self._default_model = model or DEFAULT_MODEL

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        messages: list[dict[str, Any]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        for m in request.messages:
            messages.append({"role": m.role, "content": m.content})

        result = self._client.chat.completions.create(
            model=request.model or self._default_model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        text = result.choices[0].message.content or ""
        return CompletionResponse(content=text, raw=result.model_dump())

    def validate_key(self) -> bool:
        try:
            self._client.chat.completions.create(
                model=self._default_model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
        except AuthenticationError:
            return False
        return True
