from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    role: str
    content: str


@dataclass
class CompletionRequest:
    messages: list[Message]
    system: str | None = None
    model: str | None = None
    temperature: float = 0.2
    max_tokens: int = 4096
    response_schema: dict[str, Any] | None = None
    tools: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CompletionResponse:
    content: str
    raw: dict[str, Any]
    input_tokens: int = 0
    output_tokens: int = 0


class LLMClient(ABC):
    @abstractmethod
    def complete(self, request: CompletionRequest) -> CompletionResponse: ...

    @abstractmethod
    def validate_key(self) -> bool: ...
