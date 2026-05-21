import asyncio
import subprocess
from pathlib import Path

import pytest

from packages.agent_runtime import (
    Agent,
    AgentMemory,
    Envelope,
    MessageBus,
    TaskAssignment,
    Workspace,
    new_envelope,
)
from packages.agents import QAAgent
from packages.agents import qa as qa_module


class StatusCollector(Agent):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.received: list[Envelope] = []

    async def handle(self, envelope: Envelope) -> None:
        self.received.append(envelope)


def _build_team(tmp_path: Path) -> tuple[QAAgent, StatusCollector, MessageBus]:
    bus = MessageBus()
    workspace = Workspace(project_id="proj-qa", root=tmp_path / "ws")
    qa = QAAgent(
        name="qa",
        role="qa",
        mailbox=bus.register("qa"),
        bus=bus,
        workspace=workspace,
        memory=AgentMemory(),
    )
    pm = StatusCollector(
        name="pm",
        role="project_manager",
        mailbox=bus.register("pm"),
        bus=bus,
        workspace=workspace,
        memory=AgentMemory(),
    )
    return qa, pm, bus


async def _drive(qa: Agent, pm: Agent, seconds: float = 0.2) -> None:
    qa_task = asyncio.create_task(qa.run())
    pm_task = asyncio.create_task(pm.run())
    try:
        await asyncio.sleep(seconds)
    finally:
        qa.shutdown()
        pm.shutdown()
        await asyncio.wait_for(asyncio.gather(qa_task, pm_task), timeout=2)


def _seed_tests(workspace_root: Path) -> Path:
    """Create a minimal backend/tests/ tree so the QA agent thinks tests exist.
    Real test execution is mocked at the subprocess layer."""
    backend = workspace_root / "project" / "backend"
    (backend / "tests").mkdir(parents=True)
    (backend / "tests" / "test_smoke.py").write_text("def test_ok(): pass\n")
    return backend


def _statuses(received: list[Envelope]) -> list[tuple[str, str]]:
    return [
        (env.payload.status, env.payload.notes or "")
        for env in received
        if env.payload.kind == "status_update"
    ]


def _send_validate(bus: MessageBus, task_id: str = "qa-1") -> None:
    asyncio.get_event_loop().run_until_complete(  # only for sync helpers, not used in async tests
        bus.deliver(
            new_envelope(
                from_agent="pm",
                to_agent="qa",
                project_id="proj-qa",
                payload=TaskAssignment(task_id=task_id, description="validate"),
            )
        )
    )


def test_qa_reports_success_when_pytest_passes(tmp_path: Path, monkeypatch):
    async def run() -> None:
        qa, pm, bus = _build_team(tmp_path)
        _seed_tests(qa.workspace.root)

        captured: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            captured.append(list(cmd))
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout="""........
======================== 8 passed in 2.34s ========================
""",
                stderr="",
            )

        monkeypatch.setattr(qa_module.subprocess, "run", fake_run)

        await bus.deliver(
            new_envelope(
                from_agent="pm",
                to_agent="qa",
                project_id="proj-qa",
                payload=TaskAssignment(task_id="qa-1", description="validate"),
            )
        )
        await _drive(qa, pm)

        statuses = _statuses(pm.received)
        assert ("accepted", "starting test run") in statuses
        completed = [
            env for env in pm.received
            if env.payload.kind == "status_update" and env.payload.status == "completed"
        ]
        assert len(completed) == 1
        note = completed[0].payload.notes
        assert "8 passed" in note
        assert "pytest passed" in note

        # Verifies it shelled out with pytest
        assert any("pytest" in part for part in captured[0])
        assert any("test_smoke" not in part for part in captured[0])  # uses target glob

    asyncio.run(run())


def test_qa_reports_failure_with_summary(tmp_path: Path, monkeypatch):
    async def run() -> None:
        qa, pm, bus = _build_team(tmp_path)
        _seed_tests(qa.workspace.root)

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                cmd,
                1,
                stdout="""tests/test_smoke.py::test_ok FAILED
FAILED tests/test_smoke.py::test_ok - AssertionError: nope
========================= 0 passed, 1 failed in 0.10s ==========================
""",
                stderr="",
            )

        monkeypatch.setattr(qa_module.subprocess, "run", fake_run)

        await bus.deliver(
            new_envelope(
                from_agent="pm",
                to_agent="qa",
                project_id="proj-qa",
                payload=TaskAssignment(task_id="qa-2", description="validate"),
            )
        )
        await _drive(qa, pm)

        failed = [
            env for env in pm.received
            if env.payload.kind == "status_update" and env.payload.status == "failed"
        ]
        assert len(failed) == 1
        note = failed[0].payload.notes
        assert "pytest failed" in note
        assert "1 failed" in note
        assert "AssertionError" in note

        assert any("pytest failed" in n for n in qa.memory.notes)

    asyncio.run(run())


def test_qa_treats_missing_tests_dir_as_pass(tmp_path: Path, monkeypatch):
    async def run() -> None:
        qa, pm, bus = _build_team(tmp_path)
        backend = qa.workspace.root / "project" / "backend"
        backend.mkdir(parents=True)  # no tests/ subdir

        # subprocess should not be called when there's no test directory
        called = {"v": False}

        def fake_run(*args, **kwargs):
            called["v"] = True
            return subprocess.CompletedProcess([], 0)

        monkeypatch.setattr(qa_module.subprocess, "run", fake_run)

        await bus.deliver(
            new_envelope(
                from_agent="pm",
                to_agent="qa",
                project_id="proj-qa",
                payload=TaskAssignment(task_id="qa-3", description="validate"),
            )
        )
        await _drive(qa, pm)

        statuses = _statuses(pm.received)
        assert any(s == "completed" and "no tests to run" in n for s, n in statuses)
        assert called["v"] is False

    asyncio.run(run())


def test_qa_reports_failure_when_backend_missing(tmp_path: Path):
    async def run() -> None:
        qa, pm, bus = _build_team(tmp_path)
        # don't create any project tree

        await bus.deliver(
            new_envelope(
                from_agent="pm",
                to_agent="qa",
                project_id="proj-qa",
                payload=TaskAssignment(task_id="qa-4", description="validate"),
            )
        )
        await _drive(qa, pm)

        statuses = _statuses(pm.received)
        assert any(s == "failed" and "backend dir not found" in n for s, n in statuses)

    asyncio.run(run())


def test_qa_handles_pytest_timeout(tmp_path: Path, monkeypatch):
    async def run() -> None:
        qa, pm, bus = _build_team(tmp_path)
        _seed_tests(qa.workspace.root)

        def fake_run(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd=["python", "-m", "pytest"], timeout=5)

        monkeypatch.setattr(qa_module.subprocess, "run", fake_run)

        await bus.deliver(
            new_envelope(
                from_agent="pm",
                to_agent="qa",
                project_id="proj-qa",
                payload=TaskAssignment(
                    task_id="qa-5",
                    description="validate",
                    inputs={"timeout_s": 5},
                ),
            )
        )
        await _drive(qa, pm)

        statuses = _statuses(pm.received)
        assert any(s == "failed" and "timeout" in n.lower() for s, n in statuses)

    asyncio.run(run())


def test_qa_handles_missing_pytest_binary(tmp_path: Path, monkeypatch):
    async def run() -> None:
        qa, pm, bus = _build_team(tmp_path)
        _seed_tests(qa.workspace.root)

        def fake_run(*args, **kwargs):
            raise FileNotFoundError("python: not found")

        monkeypatch.setattr(qa_module.subprocess, "run", fake_run)

        await bus.deliver(
            new_envelope(
                from_agent="pm",
                to_agent="qa",
                project_id="proj-qa",
                payload=TaskAssignment(task_id="qa-6", description="validate"),
            )
        )
        await _drive(qa, pm)

        statuses = _statuses(pm.received)
        assert any(s == "failed" and "could not invoke pytest" in n for s, n in statuses)

    asyncio.run(run())


def test_qa_records_completion_in_memory(tmp_path: Path, monkeypatch):
    async def run() -> None:
        qa, pm, bus = _build_team(tmp_path)
        _seed_tests(qa.workspace.root)
        monkeypatch.setattr(
            qa_module.subprocess,
            "run",
            lambda *a, **kw: subprocess.CompletedProcess(
                [],
                0,
                stdout="===== 3 passed in 0.50s =====\n",
            ),
        )

        await bus.deliver(
            new_envelope(
                from_agent="pm",
                to_agent="qa",
                project_id="proj-qa",
                payload=TaskAssignment(task_id="qa-7", description="validate"),
            )
        )
        await _drive(qa, pm)

        done = [t for t in qa.memory.completed_tasks if t.task_id == "qa-7"]
        assert len(done) == 1
        assert "passed" in done[0].summary


def test_qa_uses_custom_subpaths_from_inputs(tmp_path: Path, monkeypatch):
    async def run() -> None:
        qa, pm, bus = _build_team(tmp_path)
        api_dir = qa.workspace.root / "out" / "api" / "spec_tests"
        api_dir.mkdir(parents=True)
        (api_dir / "test_x.py").write_text("def test_ok(): pass\n")

        seen_cwd: list[str] = []

        def fake_run(cmd, **kwargs):
            seen_cwd.append(kwargs.get("cwd"))
            return subprocess.CompletedProcess(
                cmd, 0, stdout="===== 1 passed in 0.01s =====\n"
            )

        monkeypatch.setattr(qa_module.subprocess, "run", fake_run)

        await bus.deliver(
            new_envelope(
                from_agent="pm",
                to_agent="qa",
                project_id="proj-qa",
                payload=TaskAssignment(
                    task_id="qa-8",
                    description="validate",
                    inputs={
                        "project_subpath": "out",
                        "backend_subpath": "api",
                        "pytest_target": "spec_tests",
                    },
                ),
            )
        )
        await _drive(qa, pm)

        statuses = _statuses(pm.received)
        assert any(s == "completed" and "1 passed" in n for s, n in statuses)
        assert any(str(api_dir.parent) in cwd for cwd in seen_cwd)

    asyncio.run(run())


def test_qa_ignores_unsupported_payload_kinds(tmp_path: Path):
    async def run() -> None:
        qa, pm, bus = _build_team(tmp_path)
        from packages.agent_runtime import Question

        await bus.deliver(
            new_envelope(
                from_agent="pm",
                to_agent="qa",
                project_id="proj-qa",
                payload=Question(topic="hi"),
            )
        )
        await _drive(qa, pm, seconds=0.1)
        assert any("ignoring unsupported" in n for n in qa.memory.notes)

    asyncio.run(run())
