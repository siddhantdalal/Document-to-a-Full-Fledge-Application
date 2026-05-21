from packages.agent_runtime.exceptions import UnknownRecipient
from packages.agent_runtime.mailbox import (
    InMemoryMailboxBackend,
    Mailbox,
    MailboxBackend,
)
from packages.agent_runtime.messages import Envelope


class MessageBus:
    """Routes envelopes between registered mailboxes and keeps an audit log."""

    def __init__(self, backend: MailboxBackend | None = None) -> None:
        self.backend = backend or InMemoryMailboxBackend()
        self._mailboxes: dict[str, Mailbox] = {}
        self._audit: list[Envelope] = []

    def register(self, agent_name: str) -> Mailbox:
        if agent_name not in self._mailboxes:
            self._mailboxes[agent_name] = Mailbox(agent_name, self.backend)
        return self._mailboxes[agent_name]

    def unregister(self, agent_name: str) -> None:
        self._mailboxes.pop(agent_name, None)

    def is_registered(self, agent_name: str) -> bool:
        return agent_name in self._mailboxes

    async def deliver(self, envelope: Envelope) -> None:
        if envelope.to_agent not in self._mailboxes:
            raise UnknownRecipient(envelope.to_agent)
        self._audit.append(envelope)
        await self._mailboxes[envelope.to_agent].put(envelope)

    def audit_log(self) -> list[Envelope]:
        return list(self._audit)

    def agents(self) -> list[str]:
        return sorted(self._mailboxes.keys())


__all__ = ["MessageBus"]
