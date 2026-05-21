import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.routers import jobs as jobs_module
from apps.api.routers import preview as preview_module
from packages.runner import Preview, PreviewError

FIXTURES = Path(__file__).parent / "fixtures"


def _make_preview(job_id: str = "abc123") -> Preview:
    return Preview(
        job_id=job_id,
        project_dir=Path("/tmp/project"),
        project_name=f"doc-to-app-{job_id}",
        compose_file=Path("/tmp/project/compose.preview.yml"),
        backend_port=18000,
        frontend_port=15173,
        started_at="2026-05-21T07:00:00+00:00",
    )


def _seed_succeeded_job(job_id: str = "abc123") -> dict:
    spec = json.loads((FIXTURES / "todo_app.spec.json").read_text())
    job = jobs_module._new_job(job_id)
    job["status"] = "succeeded"
    job["spec"] = spec
    job["artifact_ready"] = True
    jobs_module._jobs[job_id] = job
    return job


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    jobs_module._jobs.clear()
    preview_module._previews.clear()
    monkeypatch.setattr(preview_module, "check_docker", lambda: None)
    return TestClient(app)


def _wait_preview(client: TestClient, job_id: str, *, target: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/jobs/{job_id}").json()
        preview = body.get("preview")
        if preview and preview["status"] == target:
            return preview
        time.sleep(0.05)
    raise AssertionError(f"preview did not reach {target} within {timeout}s")


def test_start_returns_starting_then_running(client: TestClient, monkeypatch):
    _seed_succeeded_job("abc123")
    monkeypatch.setattr(preview_module, "start_preview", lambda jid, _pd: _make_preview(jid))

    res = client.post("/jobs/abc123/preview/start")
    assert res.status_code == 200
    assert res.json()["status"] == "starting"

    final = _wait_preview(client, "abc123", target="running")
    assert final["frontend_url"] == "http://localhost:15173"
    assert final["backend_url"] == "http://localhost:18000"
    assert final["error"] is None
    assert "abc123" in preview_module._previews


def test_start_failure_marks_preview_failed(client: TestClient, monkeypatch):
    _seed_succeeded_job("abc123")

    def boom(_jid, _pd):
        raise PreviewError("port already in use")

    monkeypatch.setattr(preview_module, "start_preview", boom)

    res = client.post("/jobs/abc123/preview/start")
    assert res.status_code == 200
    final = _wait_preview(client, "abc123", target="failed")
    assert "port already in use" in final["error"]
    assert "abc123" not in preview_module._previews


def test_start_404_when_job_missing(client: TestClient):
    res = client.post("/jobs/nope/preview/start")
    assert res.status_code == 404


def test_start_409_when_artifact_not_ready(client: TestClient):
    job = jobs_module._new_job("abc123")
    jobs_module._jobs["abc123"] = job
    res = client.post("/jobs/abc123/preview/start")
    assert res.status_code == 409


def test_start_503_when_docker_unavailable(client: TestClient, monkeypatch):
    _seed_succeeded_job("abc123")
    monkeypatch.setattr(preview_module, "check_docker", lambda: "docker CLI not found")
    res = client.post("/jobs/abc123/preview/start")
    assert res.status_code == 503
    assert "docker" in res.json()["detail"].lower()


def test_stop_removes_preview_and_clears_job_field(client: TestClient, monkeypatch):
    _seed_succeeded_job("abc123")
    preview = _make_preview("abc123")
    preview_module._previews["abc123"] = preview
    jobs_module._jobs["abc123"]["preview"] = preview_module._public(preview)

    stop_calls: list[Preview] = []
    monkeypatch.setattr(preview_module, "stop_preview", lambda p: stop_calls.append(p))

    res = client.post("/jobs/abc123/preview/stop")
    assert res.status_code == 200
    assert res.json() == {"status": "stopped"}
    assert stop_calls == [preview]
    assert "abc123" not in preview_module._previews
    assert jobs_module._jobs["abc123"]["preview"] is None


def test_stop_is_no_op_when_no_active_preview(client: TestClient):
    _seed_succeeded_job("abc123")
    res = client.post("/jobs/abc123/preview/stop")
    assert res.status_code == 200


def test_logs_returns_lines(client: TestClient, monkeypatch):
    _seed_succeeded_job("abc123")
    preview = _make_preview("abc123")
    preview_module._previews["abc123"] = preview

    monkeypatch.setattr(
        preview_module,
        "fetch_logs",
        lambda p, tail=200: [f"backend | line {i}" for i in range(min(tail, 3))],
    )
    res = client.get("/jobs/abc123/preview/logs?tail=3")
    assert res.status_code == 200
    assert res.json()["lines"] == ["backend | line 0", "backend | line 1", "backend | line 2"]


def test_logs_404_when_no_active_preview(client: TestClient):
    _seed_succeeded_job("abc123")
    res = client.get("/jobs/abc123/preview/logs")
    assert res.status_code == 404


def test_starting_a_new_preview_stops_any_existing(client: TestClient, monkeypatch):
    _seed_succeeded_job("first")
    _seed_succeeded_job("second")

    monkeypatch.setattr(preview_module, "start_preview", lambda jid, _pd: _make_preview(jid))
    stop_calls: list[Preview] = []
    monkeypatch.setattr(preview_module, "stop_preview", lambda p: stop_calls.append(p))

    client.post("/jobs/first/preview/start")
    _wait_preview(client, "first", target="running")

    client.post("/jobs/second/preview/start")
    _wait_preview(client, "second", target="running")

    assert len(stop_calls) == 1
    assert stop_calls[0].job_id == "first"
    assert "first" not in preview_module._previews
    assert "second" in preview_module._previews
