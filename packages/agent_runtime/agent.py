import asyncio
import logging
from abc import ABC, abstractmethod

from packages.agent_runtime.bus import MessageBus
from packages.agent_runtime.mailbox import Mailbox
from packages.agent_runtime.memory import AgentMemory
from packages.agent_runtime.messages import Envelope, Payload, new_envelope
from packages.agent_runtime.tools import ToolSet
from packages.agent_runtime.workspace import Workspace

_log = logging.getLogger(__name__)


class Agent(ABC):
    def __init__(
        self,
        *,
        name: str,
        role: str,
        mailbox: Mailbox,
        bus: MessageBus,
        workspace: Workspace,
        memory: AgentMemory | None = None,
        tools: ToolSet | None = None,
    ) -> None:
        self.name = name
        self.role = role
        self.mailbox = mailbox
        self.bus = bus
        self.workspace = workspace
        self.memory = memory or AgentMemory()
        self.tools = tools or ToolSet(owner=name)
        self._shutdown_requested = asyncio.Event()

    @abstractmethod
    async def handle(self, envelope: Envelope) -> None:
        """Process a single envelope. Subclasses implement role-specific logic."""

    async def on_error(self, envelope: Envelope, exc: Exception) -> None:
        """Default error handler — records to memory; subclasses may override
        to escalate to PM, retry, etc."""
        _log.exception(
            "Agent %s failed handling envelope %s: %s", self.name, envelope.id, exc
        )
        self.memory.add_note(
            f"error handling envelope {envelope.id} "
            f"(kind={envelope.payload.kind}): {exc}"
        )

    async def send(
        self,
        *,
        to: str,
        payload: Payload,
        in_reply_to: str | None = None,
    ) -> str:
        envelope = new_envelope(
            from_agent=self.name,
            to_agent=to,
            project_id=self.workspace.project_id,
            payload=payload,
            in_reply_to=in_reply_to,
        )
        await self.bus.deliver(envelope)
        return envelope.id

    async def reply(self, source: Envelope, payload: Payload) -> str:
        return await self.send(
            to=source.from_agent, payload=payload, in_reply_to=source.id
        )

    async def run(self) -> None:
        """Main loop. Blocks on the mailbox; handles messages until shutdown."""
        next_task: asyncio.Task[Envelope] | None = None
        shutdown_task = asyncio.create_task(self._shutdown_requested.wait())
        try:
            while not self._shutdown_requested.is_set():
                if next_task is None:
                    next_task = asyncio.create_task(self.mailbox.next())
                done, _pending = await asyncio.wait(
                    {next_task, shutdown_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if self._shutdown_requested.is_set():
                    break
                if next_task in done:
                    envelope = next_task.result()
                    next_task = None
                    try:
                        await self.handle(envelope)
                    except Exception as exc:  # noqa: BLE001
                        await self.on_error(envelope, exc)
                    finally:
                        await self.mailbox.ack(envelope.id)
        finally:
            if next_task is not None and not next_task.done():
                next_task.cancel()
            shutdown_task.cancel()

    def shutdown(self) -> None:
        self._shutdown_requested.set()


__all__ = ["Agent"]
