import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.routers import jobs as jobs_module
from apps.api.routers import push as push_module
from packages.publisher import PushError, PushResult

FIXTURES = Path(__file__).parent / "fixtures"


def _seed_succeeded_job(job_id: str = "abc123") -> dict:
    spec = json.loads((FIXTURES / "todo_app.spec.json").read_text())
    job = jobs_module._new_job(job_id)
    job["status"] = "succeeded"
    job["spec"] = spec
    job["artifact_ready"] = True
    jobs_module._jobs[job_id] = job
    return job


@pytest.fixture
def client() -> TestClient:
    jobs_module._jobs.clear()
    return TestClient(app)


def test_push_success(client, monkeypatch):
    _seed_succeeded_job("abc123")

    captured = {}

    def fake_push(**kwargs):
        captured.update(kwargs)
        return PushResult(
            repo_url="https://github.com/siddhantdalal/todo-app",
            branch="main",
            commit_sha="deadbeef",
        )

    monkeypatch.setattr(push_module, "push_to_github", fake_push)

    res = client.post(
        "/jobs/abc123/push",
        json={
            "token": "ghp_token",
            "owner": "siddhantdalal",
            "repo": "todo-app",
            "private": True,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body == {
        "repo_url": "https://github.com/siddhantdalal/todo-app",
        "branch": "main",
        "commit_sha": "deadbeef",
    }
    assert captured["token"] == "ghp_token"
    assert captured["owner"] == "siddhantdalal"
    assert captured["repo"] == "todo-app"
    assert captured["private"] is True
    assert "Todo App" in captured["commit_message"]


def test_push_404_when_job_missing(client):
    res = client.post(
        "/jobs/nope/push",
        json={"token": "x", "owner": "siddhantdalal", "repo": "todo-app"},
    )
    assert res.status_code == 404


def test_push_409_when_artifact_not_ready(client):
    jobs_module._jobs["abc123"] = jobs_module._new_job("abc123")
    res = client.post(
        "/jobs/abc123/push",
        json={"token": "x", "owner": "siddhantdalal", "repo": "todo-app"},
    )
    assert res.status_code == 409


def test_push_400_on_publisher_error(client, monkeypatch):
    _seed_succeeded_job("abc123")

    def fake_push(**kwargs):
        raise PushError("Repo already exists.")

    monkeypatch.setattr(push_module, "push_to_github", fake_push)

    res = client.post(
        "/jobs/abc123/push",
        json={"token": "x", "owner": "siddhantdalal", "repo": "todo-app"},
    )
    assert res.status_code == 400
    assert "already exists" in res.json()["detail"]


def test_push_validates_request_body(client):
    _seed_succeeded_job("abc123")
    res = client.post(
        "/jobs/abc123/push",
        json={"token": "", "owner": "siddhantdalal", "repo": "todo-app"},
    )
    assert res.status_code == 422
