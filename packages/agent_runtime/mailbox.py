import asyncio
from collections import defaultdict
from typing import Protocol

from packages.agent_runtime.exceptions import MailboxClosed
from packages.agent_runtime.messages import Envelope


class MailboxBackend(Protocol):
    async def put(self, owner: str, envelope: Envelope) -> None: ...
    async def next(self, owner: str) -> Envelope: ...
    async def ack(self, owner: str, envelope_id: str) -> None: ...
    def history(self, owner: str) -> list[Envelope]: ...
    def pending(self, owner: str) -> list[Envelope]: ...


class InMemoryMailboxBackend:
    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[Envelope]] = {}
        self._history: dict[str, list[Envelope]] = defaultdict(list)
        self._pending: dict[str, dict[str, Envelope]] = defaultdict(dict)
        self._closed: set[str] = set()

    def _queue(self, owner: str) -> asyncio.Queue[Envelope]:
        if owner not in self._queues:
            self._queues[owner] = asyncio.Queue()
        return self._queues[owner]

    async def put(self, owner: str, envelope: Envelope) -> None:
        if owner in self._closed:
            raise MailboxClosed(f"mailbox '{owner}' is closed")
        self._history[owner].append(envelope)
        await self._queue(owner).put(envelope)

    async def next(self, owner: str) -> Envelope:
        envelope = await self._queue(owner).get()
        self._pending[owner][envelope.id] = envelope
        return envelope

    async def ack(self, owner: str, envelope_id: str) -> None:
        self._pending[owner].pop(envelope_id, None)

    def history(self, owner: str) -> list[Envelope]:
        return list(self._history[owner])

    def pending(self, owner: str) -> list[Envelope]:
        return list(self._pending[owner].values())

    def close(self, owner: str) -> None:
        self._closed.add(owner)


class Mailbox:
    def __init__(self, owner: str, backend: MailboxBackend) -> None:
        self.owner = owner
        self.backend = backend

    async def put(self, envelope: Envelope) -> None:
        await self.backend.put(self.owner, envelope)

    async def next(self) -> Envelope:
        return await self.backend.next(self.owner)

    async def ack(self, envelope_id: str) -> None:
        await self.backend.ack(self.owner, envelope_id)

    def history(self) -> list[Envelope]:
        return self.backend.history(self.owner)

    def pending(self) -> list[Envelope]:
        return self.backend.pending(self.owner)


__all__ = ["InMemoryMailboxBackend", "Mailbox", "MailboxBackend"]
