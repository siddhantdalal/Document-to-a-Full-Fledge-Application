class AgentRuntimeError(Exception):
    pass


class UnknownRecipient(AgentRuntimeError):
    def __init__(self, recipient: str) -> None:
        super().__init__(f"No mailbox registered for agent '{recipient}'.")
        self.recipient = recipient


class OwnershipViolation(AgentRuntimeError):
    def __init__(self, agent_role: str, path: str) -> None:
        super().__init__(f"Agent role '{agent_role}' is not allowed to write '{path}'.")
        self.agent_role = agent_role
        self.path = path


class ToolNotAvailable(AgentRuntimeError):
    def __init__(self, agent_name: str, tool: str) -> None:
        super().__init__(f"Tool '{tool}' is not available to agent '{agent_name}'.")
        self.agent_name = agent_name
        self.tool = tool


class MailboxClosed(AgentRuntimeError):
    pass


__all__ = [
    "AgentRuntimeError",
    "MailboxClosed",
    "OwnershipViolation",
    "ToolNotAvailable",
    "UnknownRecipient",
]
