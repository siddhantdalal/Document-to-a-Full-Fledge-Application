import asyncio
import json
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
from packages.agents import EngineerAgent
from packages.agents import engineer as engineer_module

FIXTURES = Path(__file__).parent / "fixtures"


class StatusCollector(Agent):
    """A minimal Agent that just records every envelope it receives."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.received: list[Envelope] = []

    async def handle(self, envelope: Envelope) -> None:
        self.received.append(envelope)


def _todo_spec() -> dict:
    return json.loads((FIXTURES / "todo_app.spec.json").read_text())


def _todo_markdown() -> str:
    return (FIXTURES / "todo_app.md").read_text()


@pytest.fixture(autouse=True)
def _patch_pipeline(monkeypatch: pytest.MonkeyPatch):
    """Replace the LLM-bound bits so tests don't make real calls."""
    from packages.spec_extractor import ExtractionResult

    spec = _todo_spec()
    usage = {"input": 1100, "output": 700, "total": 1800}

    def fake_extract(_markdown, _llm, retries=2, max_tokens_budget=None):
        if max_tokens_budget is not None and usage["total"] > max_tokens_budget:
            from packages.spec_extractor import SpecExtractionError

            raise SpecExtractionError(
                f"Token budget {max_tokens_budget} exceeded ({usage['total']} used)."
            )
        return ExtractionResult(spec=spec, usage=usage)

    class FakeClient:
        def __init__(self, *_args, **_kwargs):
            pass

    monkeypatch.setattr(engineer_module, "extract_spec", fake_extract)
    monkeypatch.setattr(engineer_module, "AnthropicClient", FakeClient)
    monkeypatch.setattr(engineer_module, "OpenAIClient", FakeClient)
    monkeypatch.setattr(engineer_module, "GeminiClient", FakeClient)


def _build_team(tmp_path: Path) -> tuple[EngineerAgent, StatusCollector, MessageBus]:
    bus = MessageBus()
    workspace = Workspace(project_id="proj-test", root=tmp_path / "ws")

    engineer = EngineerAgent(
        name="engineer",
        role="engineer",
        mailbox=bus.register("engineer"),
        bus=bus,
        workspace=workspace,
        memory=AgentMemory(),
    )
    collector = StatusCollector(
        name="pm",
        role="project_manager",
        mailbox=bus.register("pm"),
        bus=bus,
        workspace=workspace,
        memory=AgentMemory(),
    )
    return engineer, collector, bus


async def _drive(engineer: Agent, collector: Agent, seconds: float = 0.6) -> None:
    e_task = asyncio.create_task(engineer.run())
    c_task = asyncio.create_task(collector.run())
    try:
        await asyncio.sleep(seconds)
    finally:
        engineer.shutdown()
        collector.shutdown()
        await asyncio.wait_for(asyncio.gather(e_task, c_task), timeout=2)


def _statuses(received: list[Envelope]) -> list[tuple[str, str]]:
    return [
        (env.payload.status, env.payload.notes or "")
        for env in received
        if env.payload.kind == "status_update"
    ]


def test_engineer_runs_pipeline_end_to_end(tmp_path: Path):
    async def run() -> None:
        engineer, collector, bus = _build_team(tmp_path)
        await bus.deliver(
            new_envelope(
                from_agent="pm",
                to_agent="engineer",
                project_id="proj-test",
                payload=TaskAssignment(
                    task_id="t-1",
                    description="ship the todo app",
                    inputs={
                        "markdown": _todo_markdown(),
                        "provider": "anthropic",
                        "model": "claude-opus-4-7",
                        "api_key": "sk-fake",
                    },
                ),
            )
        )
        await _drive(engineer, collector)

        statuses = _statuses(collector.received)
        assert ("accepted", "task received") in statuses
        assert any(s == "in_progress" and "extract" in n for s, n in statuses)
        assert any(s == "in_progress" and "generat" in n for s, n in statuses)
        assert any(s == "in_progress" and "validat" in n for s, n in statuses)
        assert any(s == "in_progress" and "reconcil" in n for s, n in statuses)
        assert any(s == "in_progress" and "packag" in n for s, n in statuses)
        completed = [
            env for env in collector.received
            if env.payload.kind == "status_update" and env.payload.status == "completed"
        ]
        assert len(completed) == 1
        completed_env = completed[0]
        assert completed_env.payload.artifact_uris
        assert "covered" in completed_env.payload.notes
        assert "1,800 tokens" not in completed_env.payload.notes  # not formatted
        assert "1800" in completed_env.payload.notes

    asyncio.run(run())


def test_engineer_writes_project_tree_and_zip(tmp_path: Path):
    async def run() -> None:
        engineer, collector, bus = _build_team(tmp_path)
        await bus.deliver(
            new_envelope(
                from_agent="pm",
                to_agent="engineer",
                project_id="proj-test",
                payload=TaskAssignment(
                    task_id="t-2",
                    description="ship",
                    inputs={
                        "markdown": _todo_markdown(),
                        "provider": "anthropic",
                        "model": "claude-opus-4-7",
                        "api_key": "sk-fake",
                    },
                ),
            )
        )
        await _drive(engineer, collector)

        ws_root = engineer.workspace.root
        assert (ws_root / "project" / "README.md").exists()
        assert (ws_root / "project" / "backend" / "app" / "main.py").exists()
        assert (ws_root / "project" / "frontend" / "package.json").exists()
        assert (ws_root / "t-2.zip").exists()

    asyncio.run(run())


def test_engineer_records_workspace_snapshot_commit(tmp_path: Path):
    async def run() -> None:
        engineer, collector, bus = _build_team(tmp_path)
        await bus.deliver(
            new_envelope(
                from_agent="pm",
                to_agent="engineer",
                project_id="proj-test",
                payload=TaskAssignment(
                    task_id="t-3",
                    description="ship",
                    inputs={
                        "markdown": _todo_markdown(),
                        "provider": "anthropic",
                        "model": "claude-opus-4-7",
                        "api_key": "sk-fake",
                    },
                ),
            )
        )
        await _drive(engineer, collector)

        commits = engineer.workspace.commits_by_agent("engineer")
        assert len(commits) == 1
        commit = commits[0]
        assert commit.agent_role == "engineer"
        assert "Todo App" in commit.message
        # Snapshot covers project files
        assert any(p.startswith("project/backend/") for p in commit.paths)
        assert any(p.startswith("project/frontend/") for p in commit.paths)

    asyncio.run(run())


def test_engineer_records_decision_and_completion_in_memory(tmp_path: Path):
    async def run() -> None:
        engineer, collector, bus = _build_team(tmp_path)
        await bus.deliver(
            new_envelope(
                from_agent="pm",
                to_agent="engineer",
                project_id="proj-test",
                payload=TaskAssignment(
                    task_id="t-4",
                    description="ship",
                    inputs={
                        "markdown": _todo_markdown(),
                        "provider": "openai",
                        "model": "gpt-4o",
                        "api_key": "sk-fake",
                    },
                ),
            )
        )
        await _drive(engineer, collector)

        assert any(
            d.related_task == "t-4" and "Todo App" in d.summary
            for d in engineer.memory.decisions
        )
        assert any(
            t.task_id == "t-4" and "shipped" in t.summary
            for t in engineer.memory.completed_tasks
        )

    asyncio.run(run())


def test_engineer_fails_gracefully_on_missing_inputs(tmp_path: Path):
    async def run() -> None:
        engineer, collector, bus = _build_team(tmp_path)
        await bus.deliver(
            new_envelope(
                from_agent="pm",
                to_agent="engineer",
                project_id="proj-test",
                payload=TaskAssignment(
                    task_id="t-bad",
                    description="ship",
                    inputs={"markdown": "x"},  # missing provider/model/api_key
                ),
            )
        )
        await _drive(engineer, collector, seconds=0.2)

        statuses = _statuses(collector.received)
        failed = [n for s, n in statuses if s == "failed"]
        assert failed
        assert "missing required inputs" in failed[0]
        # No project was written
        assert not (engineer.workspace.root / "project").exists()

    asyncio.run(run())


def test_engineer_respects_token_budget(tmp_path: Path):
    async def run() -> None:
        engineer, collector, bus = _build_team(tmp_path)
        await bus.deliver(
            new_envelope(
                from_agent="pm",
                to_agent="engineer",
                project_id="proj-test",
                payload=TaskAssignment(
                    task_id="t-budget",
                    description="ship",
                    inputs={
                        "markdown": _todo_markdown(),
                        "provider": "anthropic",
                        "model": "claude-opus-4-7",
                        "api_key": "sk-fake",
                        "max_tokens": 100,
                    },
                ),
            )
        )
        await _drive(engineer, collector, seconds=0.3)

        statuses = _statuses(collector.received)
        assert any(s == "failed" and "extract_spec" in n for s, n in statuses)

    asyncio.run(run())


def test_engineer_ignores_unknown_payload_kinds(tmp_path: Path):
    async def run() -> None:
        engineer, _collector, bus = _build_team(tmp_path)
        from packages.agent_runtime import Heartbeat, Question

        await bus.deliver(
            new_envelope(
                from_agent="pm",
                to_agent="engineer",
                project_id="proj-test",
                payload=Heartbeat(),
            )
        )
        await bus.deliver(
            new_envelope(
                from_agent="pm",
                to_agent="engineer",
                project_id="proj-test",
                payload=Question(topic="random"),
            )
        )
        await _drive(engineer, _collector, seconds=0.15)
        # No project written, but no crash
        assert not (engineer.workspace.root / "project").exists()
        # Question got a note in memory
        assert any(
            "ignoring unsupported" in n and "question" in n
            for n in engineer.memory.notes
        )

    asyncio.run(run())
