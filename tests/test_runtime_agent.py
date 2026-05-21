import asyncio
from pathlib import Path

import pytest

from packages.agent_runtime import (
    Agent,
    AgentMemory,
    Answer,
    Envelope,
    FnTool,
    Heartbeat,
    MessageBus,
    Question,
    TaskAssignment,
    ToolNotAvailable,
    ToolSet,
    UnknownRecipient,
    Workspace,
    new_envelope,
)


class EchoAgent(Agent):
    """Records every envelope and echoes Question -> Answer."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.received: list[Envelope] = []

    async def handle(self, envelope: Envelope) -> None:
        self.received.append(envelope)
        payload = envelope.payload
        if payload.kind == "question":
            await self.reply(envelope, Answer(content=f"echo: {payload.topic}"))


class FailingAgent(Agent):
    async def handle(self, envelope: Envelope) -> None:
        raise RuntimeError("deliberate failure")


async def _run_for(agent: Agent, seconds: float = 0.2) -> None:
    task = asyncio.create_task(agent.run())
    try:
        await asyncio.sleep(seconds)
    finally:
        agent.shutdown()
        await asyncio.wait_for(task, timeout=1)


def _make(tmp_path: Path, name: str, role: str = "engineer") -> tuple[Agent, MessageBus]:
    bus = MessageBus()
    workspace = Workspace(project_id="p1", root=tmp_path)
    agent = EchoAgent(
        name=name,
        role=role,
        mailbox=bus.register(name),
        bus=bus,
        workspace=workspace,
        memory=AgentMemory(),
        tools=ToolSet(owner=name),
    )
    return agent, bus


def test_agent_handles_delivered_envelope(tmp_path: Path):
    async def run() -> None:
        agent, bus = _make(tmp_path, "alice")
        await bus.deliver(
            new_envelope(
                from_agent="user",
                to_agent="alice",
                project_id="p1",
                payload=Heartbeat(note="hi"),
            )
        )
        await _run_for(agent)
        assert len(agent.received) == 1
        assert agent.received[0].payload.kind == "heartbeat"

    asyncio.run(run())


def test_agent_can_reply(tmp_path: Path):
    async def run() -> None:
        # Set up alice (echoes) and bob (sender + listener)
        bus = MessageBus()
        workspace = Workspace(project_id="p1", root=tmp_path)
        alice = EchoAgent(
            name="alice",
            role="engineer",
            mailbox=bus.register("alice"),
            bus=bus,
            workspace=workspace,
            memory=AgentMemory(),
        )
        bob = EchoAgent(
            name="bob",
            role="engineer",
            mailbox=bus.register("bob"),
            bus=bus,
            workspace=workspace,
            memory=AgentMemory(),
        )
        question = new_envelope(
            from_agent="bob",
            to_agent="alice",
            project_id="p1",
            payload=Question(topic="ping"),
        )
        await bus.deliver(question)
        task_a = asyncio.create_task(alice.run())
        task_b = asyncio.create_task(bob.run())
        try:
            await asyncio.sleep(0.2)
        finally:
            alice.shutdown()
            bob.shutdown()
            await asyncio.gather(task_a, task_b)

        # Bob received the Answer
        assert any(
            env.payload.kind == "answer" and env.in_reply_to == question.id
            for env in bob.received
        )
        # Audit log captured both messages
        kinds = sorted(env.payload.kind for env in bus.audit_log())
        assert kinds == ["answer", "question"]

    asyncio.run(run())


def test_deliver_to_unknown_recipient_raises(tmp_path: Path):
    async def run() -> None:
        bus = MessageBus()
        with pytest.raises(UnknownRecipient):
            await bus.deliver(
                new_envelope(
                    from_agent="x",
                    to_agent="ghost",
                    project_id="p1",
                    payload=Heartbeat(),
                )
            )

    asyncio.run(run())


def test_agent_acks_messages_after_handling(tmp_path: Path):
    async def run() -> None:
        agent, bus = _make(tmp_path, "alice")
        await bus.deliver(
            new_envelope(
                from_agent="x",
                to_agent="alice",
                project_id="p1",
                payload=Heartbeat(),
            )
        )
        await _run_for(agent)
        # After ack, no pending messages remain
        assert agent.mailbox.pending() == []

    asyncio.run(run())


def test_agent_errors_recorded_and_envelope_acked(tmp_path: Path):
    async def run() -> None:
        bus = MessageBus()
        workspace = Workspace(project_id="p1", root=tmp_path)
        agent = FailingAgent(
            name="grumpy",
            role="engineer",
            mailbox=bus.register("grumpy"),
            bus=bus,
            workspace=workspace,
            memory=AgentMemory(),
        )
        await bus.deliver(
            new_envelope(
                from_agent="x",
                to_agent="grumpy",
                project_id="p1",
                payload=Heartbeat(),
            )
        )
        await _run_for(agent)
        assert any("error handling" in note for note in agent.memory.notes)
        # The pipeline didn't stall — pending mailbox is empty
        assert agent.mailbox.pending() == []

    asyncio.run(run())


def test_audit_log_records_every_delivery(tmp_path: Path):
    async def run() -> None:
        agent, bus = _make(tmp_path, "alice")
        for i in range(3):
            await bus.deliver(
                new_envelope(
                    from_agent="user",
                    to_agent="alice",
                    project_id="p1",
                    payload=Heartbeat(note=f"ping-{i}"),
                )
            )
        await _run_for(agent)
        assert len(bus.audit_log()) == 3
        assert [env.to_agent for env in bus.audit_log()] == ["alice"] * 3

    asyncio.run(run())


def test_tool_dispatch_through_toolset():
    async def run() -> None:
        async def add(*, a: int, b: int) -> int:
            return a + b

        tools = ToolSet(owner="x", tools={"add": FnTool(name="add", fn=add)})
        assert await tools.call("add", a=2, b=3) == 5
        assert tools.available() == ["add"]

    asyncio.run(run())


def test_tool_not_available_raises():
    async def run() -> None:
        tools = ToolSet(owner="x")
        with pytest.raises(ToolNotAvailable):
            await tools.call("nope")

    asyncio.run(run())


def test_agent_shutdown_stops_the_loop(tmp_path: Path):
    async def run() -> None:
        agent, _bus = _make(tmp_path, "alice")
        task = asyncio.create_task(agent.run())
        await asyncio.sleep(0.05)
        agent.shutdown()
        await asyncio.wait_for(task, timeout=1)
        assert task.done()

    asyncio.run(run())


def test_task_assignment_payload_can_be_delivered(tmp_path: Path):
    async def run() -> None:
        agent, bus = _make(tmp_path, "engineer")
        await bus.deliver(
            new_envelope(
                from_agent="pm",
                to_agent="engineer",
                project_id="p1",
                payload=TaskAssignment(task_id="t-1", description="implement /users"),
            )
        )
        await _run_for(agent)
        assert agent.received[0].payload.kind == "task_assignment"
        assert agent.received[0].payload.task_id == "t-1"

    asyncio.run(run())
