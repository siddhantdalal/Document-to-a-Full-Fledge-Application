import asyncio
import uuid
from pathlib import Path
from typing import Any

from packages.agent_runtime import (
    Agent,
    AgentMemory,
    Envelope,
    MessageBus,
    UserMessage,
    Workspace,
    new_envelope,
)
from packages.agents.engineer import EngineerAgent
from packages.agents.pm import PMAgent
from packages.agents.product_owner import POAgent
from packages.agents.qa import QAAgent
from packages.ai_providers.anthropic_client import AnthropicClient
from packages.ai_providers.base import LLMClient
from packages.ai_providers.gemini_client import GeminiClient
from packages.ai_providers.openai_client import OpenAIClient


def make_llm_client(provider: str, api_key: str, model: str) -> LLMClient:
    if provider == "anthropic":
        return AnthropicClient(api_key=api_key, model=model)
    if provider == "openai":
        return OpenAIClient(api_key=api_key, model=model)
    if provider == "gemini":
        return GeminiClient(api_key=api_key, model=model)
    raise ValueError(f"Unsupported provider: {provider}")


class UserInboxAgent(Agent):
    """A passive Agent whose sole job is to receive UserReply envelopes
    from the PO so the orchestrator can hand them to the HTTP layer."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._inbox: list[Envelope] = []
        self._cursor = 0

    async def handle(self, envelope: Envelope) -> None:
        self._inbox.append(envelope)

    def drain(self) -> list[Envelope]:
        new = self._inbox[self._cursor :]
        self._cursor = len(self._inbox)
        return new

    def all_replies(self) -> list[Envelope]:
        return list(self._inbox)


class Project:
    """Owns one multi-agent team for a single user-facing project. Wires
    the four core agents (PO, PM, Engineer, QA) plus a UserInboxAgent that
    captures replies destined for the user.

    Lifecycle:
        project = Project(...)
        await project.start()
        ...
        await project.send_user_message("I want a todo app.")
        replies = project.drain_user_replies()
        ...
        await project.stop()
    """

    def __init__(
        self,
        *,
        project_id: str | None = None,
        workspace_root: Path,
        provider: str,
        model: str,
        api_key: str,
        max_tokens_budget: int | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.id = project_id or f"proj-{uuid.uuid4().hex[:12]}"
        self.workspace = Workspace(
            project_id=self.id, root=Path(workspace_root) / self.id
        )
        self.bus = MessageBus()

        self._llm = llm_client or make_llm_client(provider, api_key, model)

        self.user_inbox = UserInboxAgent(
            name="user",
            role="user",
            mailbox=self.bus.register("user"),
            bus=self.bus,
            workspace=self.workspace,
            memory=AgentMemory(),
        )
        self.po = POAgent(
            llm=self._llm,
            provider=provider,
            model=model,
            api_key=api_key,
            max_tokens_budget=max_tokens_budget,
            name="po",
            role="product_owner",
            mailbox=self.bus.register("po"),
            bus=self.bus,
            workspace=self.workspace,
            memory=AgentMemory(),
        )
        self.pm = PMAgent(
            name="pm",
            role="project_manager",
            mailbox=self.bus.register("pm"),
            bus=self.bus,
            workspace=self.workspace,
            memory=AgentMemory(),
        )
        self.engineer = EngineerAgent(
            name="engineer",
            role="engineer",
            mailbox=self.bus.register("engineer"),
            bus=self.bus,
            workspace=self.workspace,
            memory=AgentMemory(),
        )
        self.qa = QAAgent(
            name="qa",
            role="qa",
            mailbox=self.bus.register("qa"),
            bus=self.bus,
            workspace=self.workspace,
            memory=AgentMemory(),
        )
        self._agents: tuple[Agent, ...] = (
            self.user_inbox,
            self.po,
            self.pm,
            self.engineer,
            self.qa,
        )
        self._tasks: list[asyncio.Task[None]] = []

    @property
    def agents(self) -> tuple[Agent, ...]:
        return self._agents

    async def start(self) -> None:
        if self._tasks:
            return
        self._tasks = [asyncio.create_task(a.run()) for a in self._agents]

    async def stop(self) -> None:
        for agent in self._agents:
            agent.shutdown()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks = []

    async def send_user_message(self, text: str) -> str:
        envelope = new_envelope(
            from_agent="user",
            to_agent="po",
            project_id=self.id,
            payload=UserMessage(text=text),
        )
        await self.bus.deliver(envelope)
        return envelope.id

    def drain_user_replies(self) -> list[Envelope]:
        return self.user_inbox.drain()

    def all_user_replies(self) -> list[Envelope]:
        return self.user_inbox.all_replies()

    def snapshot(self) -> dict[str, Any]:
        """Cheap read-only state useful for an HTTP GET /projects/{id} endpoint."""
        return {
            "id": self.id,
            "agents": [
                {
                    "name": a.name,
                    "role": a.role,
                    "decisions": len(a.memory.decisions),
                    "completed_tasks": len(a.memory.completed_tasks),
                    "open_questions": len(a.memory.open_questions),
                    "notes": len(a.memory.notes),
                }
                for a in self._agents
            ],
            "brief_present": self.workspace.exists("brief.md"),
            "artifacts": self.workspace.list_files("*.zip"),
            "active_workflows": self.pm.active_workflows,
            "audit_length": len(self.bus.audit_log()),
        }


__all__ = ["Project", "UserInboxAgent", "make_llm_client"]
