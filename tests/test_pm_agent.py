import asyncio
from pathlib import Path

from packages.agent_runtime import (
    Agent,
    AgentMemory,
    Envelope,
    MessageBus,
    StatusUpdate,
    TaskAssignment,
    Workspace,
    new_envelope,
)
from packages.agents import PMAgent


class FakeWorker(Agent):
    """Test double for Engineer or QA. Each TaskAssignment is answered with
    a single StatusUpdate using the pre-configured outcome and notes."""

    def __init__(
        self,
        *,
        outcome: str = "completed",
        outcome_notes: str = "ok",
        artifact_uri: str | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.outcome = outcome
        self.outcome_notes = outcome_notes
        self.artifact_uri = artifact_uri
        self.received: list[Envelope] = []

    async def handle(self, envelope: Envelope) -> None:
        self.received.append(envelope)
        if envelope.payload.kind != "task_assignment":
            return
        task = envelope.payload
        await self.send(
            to=envelope.from_agent,
            payload=StatusUpdate(
                task_id=task.task_id,
                status=self.outcome,  # type: ignore[arg-type]
                notes=self.outcome_notes,
                artifact_uris=[self.artifact_uri] if self.artifact_uri else [],
            ),
            in_reply_to=envelope.id,
        )


class StatusCollector(Agent):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.received: list[Envelope] = []

    async def handle(self, envelope: Envelope) -> None:
        self.received.append(envelope)


def _build_team(
    tmp_path: Path,
    *,
    engineer_outcome: str = "completed",
    engineer_notes: str = "shipped 11/11 spec items",
    qa_outcome: str = "completed",
    qa_notes: str = "5 passed",
) -> tuple[PMAgent, FakeWorker, FakeWorker, StatusCollector, MessageBus]:
    bus = MessageBus()
    workspace = Workspace(project_id="proj-pm", root=tmp_path / "ws")

    pm = PMAgent(
        name="pm",
        role="project_manager",
        mailbox=bus.register("pm"),
        bus=bus,
        workspace=workspace,
        memory=AgentMemory(),
    )
    engineer = FakeWorker(
        outcome=engineer_outcome,
        outcome_notes=engineer_notes,
        artifact_uri="/tmp/proj-pm/t-1.zip" if engineer_outcome == "completed" else None,
        name="engineer",
        role="engineer",
        mailbox=bus.register("engineer"),
        bus=bus,
        workspace=workspace,
        memory=AgentMemory(),
    )
    qa = FakeWorker(
        outcome=qa_outcome,
        outcome_notes=qa_notes,
        name="qa",
        role="qa",
        mailbox=bus.register("qa"),
        bus=bus,
        workspace=workspace,
        memory=AgentMemory(),
    )
    user = StatusCollector(
        name="user",
        role="user",
        mailbox=bus.register("user"),
        bus=bus,
        workspace=workspace,
        memory=AgentMemory(),
    )
    return pm, engineer, qa, user, bus


async def _drive(*agents: Agent, seconds: float = 0.3) -> None:
    tasks = [asyncio.create_task(a.run()) for a in agents]
    try:
        await asyncio.sleep(seconds)
    finally:
        for a in agents:
            a.shutdown()
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=2)


def _statuses(received: list[Envelope]) -> list[tuple[str, str]]:
    return [
        (env.payload.status, env.payload.notes or "")
        for env in received
        if env.payload.kind == "status_update"
    ]


def _deliver_task(
    bus: MessageBus, task_id: str = "t-1", inputs: dict | None = None
) -> str:
    env = new_envelope(
        from_agent="user",
        to_agent="pm",
        project_id="proj-pm",
        payload=TaskAssignment(
            task_id=task_id,
            description="ship the app",
            inputs=inputs
            or {
                "markdown": "# App",
                "provider": "anthropic",
                "model": "claude-opus-4-7",
                "api_key": "sk-fake",
            },
        ),
    )

    async def deliver() -> str:
        await bus.deliver(env)
        return env.id

    return asyncio.get_event_loop().run_until_complete(deliver())


def test_happy_path_engineer_then_qa(tmp_path: Path):
    async def run() -> None:
        pm, engineer, qa, user, bus = _build_team(tmp_path)
        await bus.deliver(
            new_envelope(
                from_agent="user",
                to_agent="pm",
                project_id="proj-pm",
                payload=TaskAssignment(
                    task_id="t-1",
                    description="ship",
                    inputs={
                        "markdown": "# App",
                        "provider": "anthropic",
                        "model": "claude-opus-4-7",
                        "api_key": "sk-fake",
                    },
                ),
            )
        )
        await _drive(pm, engineer, qa, user)

        statuses = _statuses(user.received)
        # User got at least: accepted -> in_progress(engineer) ->
        # in_progress(qa) -> completed
        assert ("accepted", "planning: engineer -> qa") in statuses
        assert any(s == "in_progress" and "engineer" in n.lower() for s, n in statuses)
        assert any(s == "in_progress" and "dispatched to qa" in n for s, n in statuses)
        completed = [
            env for env in user.received
            if env.payload.kind == "status_update" and env.payload.status == "completed"
        ]
        assert len(completed) == 1
        assert "engineer + qa both passed" in completed[0].payload.notes
        assert completed[0].payload.artifact_uris == ["/tmp/proj-pm/t-1.zip"]

        # Engineer got the original inputs forwarded
        eng_assignment = next(
            env for env in engineer.received
            if env.payload.kind == "task_assignment"
        )
        assert eng_assignment.payload.task_id == "t-1.eng"
        assert eng_assignment.payload.inputs["api_key"] == "sk-fake"

        # QA got a fresh task with defaults (no inputs)
        qa_assignment = next(
            env for env in qa.received
            if env.payload.kind == "task_assignment"
        )
        assert qa_assignment.payload.task_id == "t-1.qa"
        assert qa_assignment.payload.inputs == {}

        # Workflow cleaned up
        assert pm.active_workflows == []

    asyncio.run(run())


def test_engineer_failure_short_circuits_workflow(tmp_path: Path):
    async def run() -> None:
        pm, engineer, qa, user, bus = _build_team(
            tmp_path,
            engineer_outcome="failed",
            engineer_notes="extract_spec failed: 401",
        )
        await bus.deliver(
            new_envelope(
                from_agent="user",
                to_agent="pm",
                project_id="proj-pm",
                payload=TaskAssignment(task_id="t-2", description="ship"),
            )
        )
        await _drive(pm, engineer, qa, user)

        statuses = _statuses(user.received)
        failed = [n for s, n in statuses if s == "failed"]
        assert len(failed) == 1
        assert "engineer failed" in failed[0]
        assert "401" in failed[0]

        # QA was never invoked
        qa_assignments = [
            env for env in qa.received if env.payload.kind == "task_assignment"
        ]
        assert qa_assignments == []
        assert pm.active_workflows == []

    asyncio.run(run())


def test_qa_failure_marks_workflow_failed(tmp_path: Path):
    async def run() -> None:
        pm, engineer, qa, user, bus = _build_team(
            tmp_path,
            qa_outcome="failed",
            qa_notes="2 failed",
        )
        await bus.deliver(
            new_envelope(
                from_agent="user",
                to_agent="pm",
                project_id="proj-pm",
                payload=TaskAssignment(task_id="t-3", description="ship"),
            )
        )
        await _drive(pm, engineer, qa, user)

        statuses = _statuses(user.received)
        failed = [n for s, n in statuses if s == "failed"]
        assert len(failed) == 1
        assert "qa failed" in failed[0]
        assert "2 failed" in failed[0]
        assert pm.active_workflows == []

    asyncio.run(run())


def test_two_workflows_in_parallel_dont_interfere(tmp_path: Path):
    async def run() -> None:
        pm, engineer, qa, user, bus = _build_team(tmp_path)
        for task_id in ("p1", "p2"):
            await bus.deliver(
                new_envelope(
                    from_agent="user",
                    to_agent="pm",
                    project_id="proj-pm",
                    payload=TaskAssignment(task_id=task_id, description="ship"),
                )
            )
        await _drive(pm, engineer, qa, user, seconds=0.4)

        completed = [
            env.payload.task_id for env in user.received
            if env.payload.kind == "status_update" and env.payload.status == "completed"
        ]
        assert sorted(completed) == ["p1", "p2"]
        assert pm.active_workflows == []

    asyncio.run(run())


def test_status_for_unknown_subtask_is_ignored(tmp_path: Path):
    async def run() -> None:
        pm, engineer, qa, user, bus = _build_team(tmp_path)

        # Send a stray status update for a subtask the PM never dispatched
        await bus.deliver(
            new_envelope(
                from_agent="engineer",
                to_agent="pm",
                project_id="proj-pm",
                payload=StatusUpdate(task_id="ghost.eng", status="completed"),
            )
        )
        await _drive(pm, engineer, qa, user, seconds=0.1)

        # PM did not crash and emitted nothing to the user
        assert user.received == []

    asyncio.run(run())


def test_pm_records_workflow_in_memory(tmp_path: Path):
    async def run() -> None:
        pm, engineer, qa, user, bus = _build_team(tmp_path)
        await bus.deliver(
            new_envelope(
                from_agent="user",
                to_agent="pm",
                project_id="proj-pm",
                payload=TaskAssignment(task_id="t-mem", description="ship"),
            )
        )
        await _drive(pm, engineer, qa, user)

        decisions = [d for d in pm.memory.decisions if d.related_task == "t-mem"]
        assert decisions and "started workflow" in decisions[0].summary
        completed = [t for t in pm.memory.completed_tasks if t.task_id == "t-mem"]
        assert completed and "both passed" in completed[0].summary

    asyncio.run(run())


def test_pm_records_failure_in_memory(tmp_path: Path):
    async def run() -> None:
        pm, engineer, qa, user, bus = _build_team(
            tmp_path,
            engineer_outcome="failed",
            engineer_notes="boom",
        )
        await bus.deliver(
            new_envelope(
                from_agent="user",
                to_agent="pm",
                project_id="proj-pm",
                payload=TaskAssignment(task_id="t-fail", description="ship"),
            )
        )
        await _drive(pm, engineer, qa, user)

        assert any(
            "t-fail" in n and "engineer" in n for n in pm.memory.notes
        )

    asyncio.run(run())


def test_pm_ignores_unsupported_payload_kinds(tmp_path: Path):
    async def run() -> None:
        pm, engineer, qa, user, bus = _build_team(tmp_path)
        from packages.agent_runtime import Question

        await bus.deliver(
            new_envelope(
                from_agent="user",
                to_agent="pm",
                project_id="proj-pm",
                payload=Question(topic="?"),
            )
        )
        await _drive(pm, engineer, qa, user, seconds=0.1)
        assert any("ignoring unsupported" in n for n in pm.memory.notes)

    asyncio.run(run())
