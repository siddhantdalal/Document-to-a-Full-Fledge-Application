import asyncio
import json
from pathlib import Path

import pytest

from packages.agents import Project
from packages.agents import engineer as engineer_module
from packages.agents import orchestrator as orchestrator_module
from packages.ai_providers.base import (
    CompletionRequest,
    CompletionResponse,
    LLMClient,
)
from packages.spec_extractor import ExtractionResult

FIXTURES = Path(__file__).parent / "fixtures"


class ScriptedLLM(LLMClient):
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    def complete(self, request: CompletionRequest) -> CompletionResponse:
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


def _fence(obj: dict) -> str:
    return f"```json\n{json.dumps(obj)}\n```"


def _todo_spec() -> dict:
    return json.loads((FIXTURES / "todo_app.spec.json").read_text())


@pytest.fixture
def patched_engineer(monkeypatch: pytest.MonkeyPatch):
    """Replace the Engineer's LLM-bound bits so the orchestrator test
    doesn't hit a real model or rely on heavy codegen."""
    spec = _todo_spec()
    usage = {"input": 1100, "output": 700, "total": 1800}

    def fake_extract(_markdown, _llm, retries=2, max_tokens_budget=None):
        return ExtractionResult(spec=spec, usage=usage)

    class FakeClient:
        def __init__(self, *_a, **_kw):
            pass

    monkeypatch.setattr(engineer_module, "extract_spec", fake_extract)
    monkeypatch.setattr(engineer_module, "AnthropicClient", FakeClient)
    monkeypatch.setattr(engineer_module, "OpenAIClient", FakeClient)
    monkeypatch.setattr(engineer_module, "GeminiClient", FakeClient)


@pytest.fixture
def patched_qa(monkeypatch: pytest.MonkeyPatch):
    """Avoid real pytest subprocess invocation in the orchestrator test."""
    import subprocess

    from packages.agents import qa as qa_module

    def fake_run(*_a, **_kw):
        return subprocess.CompletedProcess(
            [],
            0,
            stdout="======== 5 passed in 1.20s ========\n",
        )

    monkeypatch.setattr(qa_module.subprocess, "run", fake_run)


def test_project_starts_and_stops_cleanly(tmp_path: Path, patched_engineer, patched_qa):
    async def run() -> None:
        llm = ScriptedLLM(responses=[])
        project = Project(
            workspace_root=tmp_path,
            provider="anthropic",
            model="claude-opus-4-7",
            api_key="sk-fake",
            llm_client=llm,
        )
        await project.start()
        await asyncio.sleep(0.05)
        await project.stop()
        # No errors, cleanup complete

    asyncio.run(run())


def test_project_user_message_flows_to_po_then_back(
    tmp_path: Path, patched_engineer, patched_qa
):
    async def run() -> None:
        llm = ScriptedLLM(
            responses=[_fence({"reply": "What features?", "handoff": None})]
        )
        project = Project(
            workspace_root=tmp_path,
            provider="anthropic",
            model="claude-opus-4-7",
            api_key="sk-fake",
            llm_client=llm,
        )
        await project.start()
        try:
            await project.send_user_message("hi")
            await asyncio.sleep(0.15)
            replies = [e.payload.text for e in project.drain_user_replies()]
            assert replies == ["What features?"]
        finally:
            await project.stop()

    asyncio.run(run())


def test_project_end_to_end_handoff_engineer_qa(
    tmp_path: Path, patched_engineer, patched_qa
):
    """The big integration: PO chats, hands off a brief, PM dispatches
    Engineer, Engineer generates + validates + reconciles + packages,
    PM dispatches QA, QA reports tests passing, PM reports completion
    to PO, PO reports done to user."""

    async def run() -> None:
        brief = "# Todo App\n\nSimple todo manager."
        llm = ScriptedLLM(
            responses=[_fence({"reply": "On it.", "handoff": {"brief": brief}})]
        )
        project = Project(
            workspace_root=tmp_path,
            provider="anthropic",
            model="claude-opus-4-7",
            api_key="sk-fake",
            llm_client=llm,
        )
        await project.start()
        try:
            await project.send_user_message("build a todo app")
            # Generous wait: codegen + validation + packaging + qa all run
            for _ in range(40):
                await asyncio.sleep(0.1)
                replies = project.all_user_replies()
                if any("Done!" in e.payload.text or "✅" in e.payload.text for e in replies):
                    break
            replies = [e.payload.text for e in project.all_user_replies()]
            assert any("On it." in r for r in replies)
            assert any("Done!" in r or "✅" in r for r in replies)
            # Brief was written
            assert project.workspace.exists("brief.md")
            # Some zip artifact was produced
            zips = project.workspace.list_files("*.zip")
            assert zips, f"no zip artifact produced, replies={replies}"
        finally:
            await project.stop()

    asyncio.run(run())


def test_project_snapshot_shows_team_health(tmp_path: Path, patched_engineer, patched_qa):
    async def run() -> None:
        llm = ScriptedLLM(
            responses=[_fence({"reply": "go", "handoff": None})]
        )
        project = Project(
            workspace_root=tmp_path,
            provider="anthropic",
            model="claude-opus-4-7",
            api_key="sk-fake",
            llm_client=llm,
        )
        await project.start()
        try:
            await project.send_user_message("hi")
            await asyncio.sleep(0.1)
            snap = project.snapshot()
            assert snap["id"] == project.id
            roles = {a["role"] for a in snap["agents"]}
            assert {"product_owner", "project_manager", "engineer", "qa"} <= roles
            assert snap["brief_present"] is False  # no handoff yet
            assert snap["audit_length"] > 0
        finally:
            await project.stop()

    asyncio.run(run())


def test_make_llm_client_dispatches_by_provider(monkeypatch):
    from packages.ai_providers import anthropic_client, openai_client

    captured = {}

    class FakeAnthropic:
        def __init__(self, *, api_key, model):
            captured["anthropic"] = (api_key, model)

    class FakeOpenAI:
        def __init__(self, *, api_key, model):
            captured["openai"] = (api_key, model)

    monkeypatch.setattr(orchestrator_module, "AnthropicClient", FakeAnthropic)
    monkeypatch.setattr(orchestrator_module, "OpenAIClient", FakeOpenAI)

    orchestrator_module.make_llm_client("anthropic", "sk-a", "claude-opus-4-7")
    orchestrator_module.make_llm_client("openai", "sk-o", "gpt-4o")

    assert captured["anthropic"] == ("sk-a", "claude-opus-4-7")
    assert captured["openai"] == ("sk-o", "gpt-4o")

    with pytest.raises(ValueError):
        orchestrator_module.make_llm_client("cohere", "x", "y")
