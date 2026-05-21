import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.routers import jobs as jobs_module

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    spec = json.loads((FIXTURES / "todo_app.spec.json").read_text())

    def fake_extract(_markdown: str, _llm) -> dict:
        return spec

    class FakeAnthropic:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

    monkeypatch.setattr(jobs_module, "extract_spec", fake_extract)
    monkeypatch.setattr(jobs_module, "AnthropicClient", FakeAnthropic)
    jobs_module._jobs.clear()
    return TestClient(app)


def _wait_done(client: TestClient, job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        res = client.get(f"/jobs/{job_id}")
        body = res.json()
        if body["status"] in ("succeeded", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError(f"Job {job_id} did not finish within {timeout}s")


def test_post_jobs_returns_pending_with_initial_stages(client: TestClient) -> None:
    with open(FIXTURES / "todo_app.md", "rb") as fh:
        res = client.post(
            "/jobs",
            files={"doc": ("todo_app.md", fh, "text/markdown")},
            data={"provider": "anthropic", "model": "claude-opus-4-7"},
            headers={"X-Provider-Key": "test-key"},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["id"]
    assert {s["name"] for s in body["stages"]} == {"extract_spec", "generate", "package"}


def test_pipeline_runs_all_stages_and_serves_zip(client: TestClient) -> None:
    with open(FIXTURES / "todo_app.md", "rb") as fh:
        res = client.post(
            "/jobs",
            files={"doc": ("todo_app.md", fh, "text/markdown")},
            data={"provider": "anthropic", "model": "claude-opus-4-7"},
            headers={"X-Provider-Key": "test-key"},
        )
    job_id = res.json()["id"]
    final = _wait_done(client, job_id)

    assert final["status"] == "succeeded"
    assert final["artifact_ready"] is True
    assert final["spec"]["app"]["name"] == "Todo App"
    assert all(s["status"] == "succeeded" for s in final["stages"])
    for stage in final["stages"]:
        assert stage["started_at"] is not None
        assert stage["finished_at"] is not None
        assert stage["message"]

    artifact = client.get(f"/jobs/{job_id}/artifact")
    assert artifact.status_code == 200
    assert artifact.headers["content-type"] == "application/zip"
    assert "todo-app.zip" in artifact.headers["content-disposition"]
    assert len(artifact.content) > 1000


def test_unknown_job_returns_404(client: TestClient) -> None:
    assert client.get("/jobs/does-not-exist").status_code == 404
    assert client.get("/jobs/does-not-exist/artifact").status_code == 404


def test_artifact_returns_409_while_pending(client: TestClient) -> None:
    jobs_module._jobs["pending-id"] = jobs_module._new_job("pending-id")
    res = client.get("/jobs/pending-id/artifact")
    assert res.status_code == 409


def test_unsupported_provider_returns_400(client: TestClient) -> None:
    with open(FIXTURES / "todo_app.md", "rb") as fh:
        res = client.post(
            "/jobs",
            files={"doc": ("todo_app.md", fh, "text/markdown")},
            data={"provider": "openai", "model": "gpt-4"},
            headers={"X-Provider-Key": "test-key"},
        )
    assert res.status_code == 400
