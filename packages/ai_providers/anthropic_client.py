from typing import Any

import anthropic

from packages.ai_providers.base import (
    CompletionRequest,
    CompletionResponse,
    LLMClient,
)

DEFAULT_MODEL = "claude-opus-4-7"


class AnthropicClient(LLMClient):
    def __init__(self, api_key: str, model: str | None = None) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._default_model = model or DEFAULT_MODEL

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        kwargs: dict[str, Any] = {
            "model": request.model or self._default_model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        }
        if request.system:
            kwargs["system"] = [
                {
                    "type": "text",
                    "text": request.system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        result = self._client.messages.create(**kwargs)
        text = "".join(block.text for block in result.content if block.type == "text")
        return CompletionResponse(content=text, raw=result.model_dump())

    def validate_key(self) -> bool:
        try:
            self._client.messages.create(
                model=self._default_model,
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
        except anthropic.AuthenticationError:
            return False
        return True
