import asyncio
import json
from pathlib import Path

from packages.agent_runtime import (
    Agent,
    AgentMemory,
    Envelope,
    MessageBus,
    StatusUpdate,
    UserMessage,
    Workspace,
    new_envelope,
)
from packages.agents import POAgent
from packages.ai_providers.base import (
    CompletionRequest,
    CompletionResponse,
    LLMClient,
)


class ScriptedLLM(LLMClient):
    """An LLMClient that returns pre-scripted responses in sequence."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        self.requests.append(request)
        if not self._responses:
            raise RuntimeError("ScriptedLLM exhausted")
        return CompletionResponse(
            content=self._responses.pop(0),
            raw={},
            input_tokens=10,
            output_tokens=20,
        )

    def validate_key(self) -> bool:
        return True


class Recorder(Agent):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.received: list[Envelope] = []

    async def handle(self, envelope: Envelope) -> None:
        self.received.append(envelope)


def _fence(obj: dict) -> str:
    return f"```json\n{json.dumps(obj)}\n```"


def _build_team(
    tmp_path: Path, responses: list[str]
) -> tuple[POAgent, Recorder, Recorder, MessageBus, ScriptedLLM]:
    bus = MessageBus()
    workspace = Workspace(project_id="proj-po", root=tmp_path / "ws")
    llm = ScriptedLLM(responses)

    po = POAgent(
        llm=llm,
        provider="anthropic",
        model="claude-opus-4-7",
        api_key="sk-fake",
        name="po",
        role="product_owner",
        mailbox=bus.register("po"),
        bus=bus,
        workspace=workspace,
        memory=AgentMemory(),
    )
    pm = Recorder(
        name="pm",
        role="project_manager",
        mailbox=bus.register("pm"),
        bus=bus,
        workspace=workspace,
        memory=AgentMemory(),
    )
    user = Recorder(
        name="user",
        role="user",
        mailbox=bus.register("user"),
        bus=bus,
        workspace=workspace,
        memory=AgentMemory(),
    )
    return po, pm, user, bus, llm


async def _drive(*agents: Agent, seconds: float = 0.15) -> None:
    tasks = [asyncio.create_task(a.run()) for a in agents]
    try:
        await asyncio.sleep(seconds)
    finally:
        for a in agents:
            a.shutdown()
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=2)


def _user_replies(received: list[Envelope]) -> list[str]:
    return [e.payload.text for e in received if e.payload.kind == "user_reply"]


def test_po_replies_with_chat_when_no_handoff(tmp_path: Path):
    async def run() -> None:
        po, pm, user, bus, _ = _build_team(
            tmp_path,
            responses=[_fence({"reply": "What features?", "handoff": None})],
        )
        await bus.deliver(
            new_envelope(
                from_agent="user",
                to_agent="po",
                project_id="proj-po",
                payload=UserMessage(text="I want a todo app"),
            )
        )
        await _drive(po, pm, user)

        replies = _user_replies(user.received)
        assert replies == ["What features?"]
        # No handoff to PM
        assert pm.received == []

    asyncio.run(run())


def test_po_hands_off_to_pm_when_brief_is_ready(tmp_path: Path):
    async def run() -> None:
        brief = "# Todo App\n\nSimple todo manager.\n## Features\n- create todos"
        po, pm, user, bus, _ = _build_team(
            tmp_path,
            responses=[
                _fence(
                    {
                        "reply": "Got it, building now.",
                        "handoff": {"brief": brief},
                    }
                )
            ],
        )
        await bus.deliver(
            new_envelope(
                from_agent="user",
                to_agent="po",
                project_id="proj-po",
                payload=UserMessage(text="Build a todo app, very simple."),
            )
        )
        await _drive(po, pm, user)

        replies = _user_replies(user.received)
        assert "Got it, building now." in replies

        # Brief written to workspace
        assert po.workspace.exists("brief.md")
        assert po.workspace.read_text("brief.md") == brief

        # TaskAssignment was sent to PM with the brief as markdown input
        assignments = [
            e for e in pm.received if e.payload.kind == "task_assignment"
        ]
        assert len(assignments) == 1
        task = assignments[0].payload
        assert task.inputs["markdown"] == brief
        assert task.inputs["provider"] == "anthropic"
        assert task.inputs["model"] == "claude-opus-4-7"
        assert task.inputs["api_key"] == "sk-fake"
        assert po.workflow_id is not None
        assert po.workflow_id == task.task_id

    asyncio.run(run())


def test_po_multi_turn_chat_history_grows(tmp_path: Path):
    async def run() -> None:
        po, pm, user, bus, llm = _build_team(
            tmp_path,
            responses=[
                _fence({"reply": "What features?", "handoff": None}),
                _fence({"reply": "And auth?", "handoff": None}),
            ],
        )
        for text in ["build me an app", "todos with users"]:
            await bus.deliver(
                new_envelope(
                    from_agent="user",
                    to_agent="po",
                    project_id="proj-po",
                    payload=UserMessage(text=text),
                )
            )
        await _drive(po, pm, user, seconds=0.2)

        assert _user_replies(user.received) == ["What features?", "And auth?"]
        # LLM saw the full conversation by the second turn
        assert len(llm.requests) == 2
        second_msgs = llm.requests[1].messages
        assert [m.content for m in second_msgs if m.role == "user"] == [
            "build me an app",
            "todos with users",
        ]
        assert any(
            "What features?" in m.content
            for m in second_msgs
            if m.role == "assistant"
        )

    asyncio.run(run())


def test_po_forwards_pm_status_updates_to_user(tmp_path: Path):
    async def run() -> None:
        brief = "# Todo App\n"
        po, pm, user, bus, _ = _build_team(
            tmp_path,
            responses=[
                _fence(
                    {
                        "reply": "On it.",
                        "handoff": {"brief": brief},
                    }
                )
            ],
        )
        tasks = [asyncio.create_task(a.run()) for a in (po, pm, user)]
        try:
            await bus.deliver(
                new_envelope(
                    from_agent="user",
                    to_agent="po",
                    project_id="proj-po",
                    payload=UserMessage(text="build a todo app"),
                )
            )
            for _ in range(20):
                await asyncio.sleep(0.02)
                if po.workflow_id:
                    break
            assert po.workflow_id is not None

            for status, notes in [
                ("accepted", "planning: engineer -> qa"),
                ("in_progress", "engineer ✓; dispatched to qa"),
                ("completed", "engineer + qa both passed"),
            ]:
                await bus.deliver(
                    new_envelope(
                        from_agent="pm",
                        to_agent="po",
                        project_id="proj-po",
                        payload=StatusUpdate(
                            task_id=po.workflow_id, status=status, notes=notes
                        ),
                    )
                )
            await asyncio.sleep(0.2)
        finally:
            for a in (po, pm, user):
                a.shutdown()
            await asyncio.gather(*tasks)

        forwarded = [
            text
            for text in _user_replies(user.received)
            if text != "On it."
        ]
        assert any("🛠" in t for t in forwarded)
        assert any("✅" in t for t in forwarded)

    asyncio.run(run())


def test_po_ignores_status_updates_for_other_workflows(tmp_path: Path):
    async def run() -> None:
        po, pm, user, bus, _ = _build_team(
            tmp_path,
            responses=[_fence({"reply": "k", "handoff": {"brief": "x"}})],
        )

        tasks = [asyncio.create_task(a.run()) for a in (po, pm, user)]
        try:
            await bus.deliver(
                new_envelope(
                    from_agent="user",
                    to_agent="po",
                    project_id="proj-po",
                    payload=UserMessage(text="build"),
                )
            )
            for _ in range(20):
                await asyncio.sleep(0.02)
                if po.workflow_id:
                    break

            before = len(user.received)
            # Stray status update for an unrelated workflow
            await bus.deliver(
                new_envelope(
                    from_agent="pm",
                    to_agent="po",
                    project_id="proj-po",
                    payload=StatusUpdate(task_id="some-other-wf", status="completed"),
                )
            )
            await asyncio.sleep(0.1)
            # No new user replies emitted for the stray status
            assert len(user.received) == before
        finally:
            for a in (po, pm, user):
                a.shutdown()
            await asyncio.gather(*tasks)

    asyncio.run(run())


def test_po_after_handoff_redirects_further_user_messages(tmp_path: Path):
    async def run() -> None:
        po, pm, user, bus, _ = _build_team(
            tmp_path,
            responses=[_fence({"reply": "k", "handoff": {"brief": "# X"}})],
        )
        for text in ["build", "and one more thing"]:
            await bus.deliver(
                new_envelope(
                    from_agent="user",
                    to_agent="po",
                    project_id="proj-po",
                    payload=UserMessage(text=text),
                )
            )
        await _drive(po, pm, user, seconds=0.2)

        replies = _user_replies(user.received)
        # First reply is the handoff one; second is the "team is building" notice
        assert any("team is already building" in r.lower() for r in replies)

    asyncio.run(run())


def test_po_gracefully_handles_unparseable_llm_output(tmp_path: Path):
    async def run() -> None:
        po, pm, user, bus, _ = _build_team(
            tmp_path,
            responses=["this is not json at all"],
        )
        await bus.deliver(
            new_envelope(
                from_agent="user",
                to_agent="po",
                project_id="proj-po",
                payload=UserMessage(text="hi"),
            )
        )
        await _drive(po, pm, user, seconds=0.1)
        # Falls back to raw content
        assert _user_replies(user.received) == ["this is not json at all"]
        # No handoff
        assert pm.received == []

    asyncio.run(run())


def test_po_handles_llm_exception(tmp_path: Path):
    class BoomLLM(LLMClient):
        def complete(self, request):
            raise RuntimeError("boom")

        def validate_key(self):
            return True

    async def run() -> None:
        bus = MessageBus()
        workspace = Workspace(project_id="proj-po", root=tmp_path / "ws")
        po = POAgent(
            llm=BoomLLM(),
            provider="anthropic",
            model="claude-opus-4-7",
            api_key="sk-fake",
            name="po",
            role="product_owner",
            mailbox=bus.register("po"),
            bus=bus,
            workspace=workspace,
            memory=AgentMemory(),
        )
        user = Recorder(
            name="user",
            role="user",
            mailbox=bus.register("user"),
            bus=bus,
            workspace=workspace,
            memory=AgentMemory(),
        )
        await bus.deliver(
            new_envelope(
                from_agent="user",
                to_agent="po",
                project_id="proj-po",
                payload=UserMessage(text="hi"),
            )
        )
        await _drive(po, user, seconds=0.1)
        replies = _user_replies(user.received)
        assert replies and "boom" in replies[0]
        assert any("LLM call failed" in n for n in po.memory.notes)

    asyncio.run(run())
