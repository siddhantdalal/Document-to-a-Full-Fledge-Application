from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from packages.agent_runtime.exceptions import ToolNotAvailable


@runtime_checkable
class Tool(Protocol):
    name: str

    async def __call__(self, **kwargs: Any) -> Any: ...


@dataclass
class FnTool:
    name: str
    fn: Callable[..., Awaitable[Any]]

    async def __call__(self, **kwargs: Any) -> Any:
        return await self.fn(**kwargs)


class ToolSet:
    """Per-agent tool registry. Acts as a whitelist."""

    def __init__(self, owner: str, tools: dict[str, Tool] | None = None) -> None:
        self.owner = owner
        self._tools: dict[str, Tool] = dict(tools or {})

    def add(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    async def call(self, name: str, **kwargs: Any) -> Any:
        if name not in self._tools:
            raise ToolNotAvailable(agent_name=self.owner, tool=name)
        return await self._tools[name](**kwargs)

    def available(self) -> list[str]:
        return sorted(self._tools.keys())


__all__ = ["FnTool", "Tool", "ToolSet"]
