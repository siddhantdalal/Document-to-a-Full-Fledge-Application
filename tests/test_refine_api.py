import copy
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.routers import jobs as jobs_module

FIXTURES = Path(__file__).parent / "fixtures"


def _todo_spec() -> dict:
    return json.loads((FIXTURES / "todo_app.spec.json").read_text())


def _refined_spec() -> dict:
    spec = _todo_spec()
    spec["entities"][1]["fields"].append({"name": "priority", "type": "string", "required": False})
    return spec


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from packages.spec_extractor import ExtractionResult

    def fake_refine(_current, change_request, _llm, retries=2, max_tokens_budget=None):
        usage = {"input": 800, "output": 400, "total": 1200}
        if max_tokens_budget is not None and usage["total"] > max_tokens_budget:
            from packages.spec_extractor import SpecExtractionError
            raise SpecExtractionError(
                f"Token budget {max_tokens_budget} exceeded ({usage['total']} used)."
            )
        return ExtractionResult(spec=_refined_spec(), usage=usage)

    class FakeClient:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

    monkeypatch.setattr(jobs_module, "refine_spec", fake_refine)
    monkeypatch.setattr(jobs_module, "AnthropicClient", FakeClient)
    monkeypatch.setattr(jobs_module, "OpenAIClient", FakeClient)
    monkeypatch.setattr(jobs_module, "GeminiClient", FakeClient)
    jobs_module._jobs.clear()
    return TestClient(app)


def _seed_parent(spec: dict | None = None) -> str:
    parent_id = "parent123"
    parent = jobs_module._new_job(parent_id)
    parent["status"] = "succeeded"
    parent["spec"] = spec or _todo_spec()
    parent["artifact_ready"] = True
    jobs_module._jobs[parent_id] = parent
    return parent_id


def _wait_done(client: TestClient, job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        res = client.get(f"/jobs/{job_id}")
        body = res.json()
        if body["status"] in ("succeeded", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError(f"Job {job_id} did not finish")


def test_refine_creates_child_job_with_diff(client: TestClient):
    parent_id = _seed_parent()
    res = client.post(
        f"/jobs/{parent_id}/refine",
        json={
            "user_message": "Add a priority field to Todo.",
            "provider": "anthropic",
            "model": "claude-opus-4-7",
        },
        headers={"X-Provider-Key": "test-key"},
    )
    assert res.status_code == 200
    body = res.json()
    child_id = body["id"]
    assert child_id != parent_id
    assert [s["name"] for s in body["stages"]] == list(jobs_module.REFINE_STAGE_NAMES)
    assert body["refinement"]["parent_job_id"] == parent_id
    assert body["refinement"]["user_message"] == "Add a priority field to Todo."

    final = _wait_done(client, child_id)
    assert final["status"] == "succeeded", final.get("error")
    assert final["artifact_ready"] is True
    refinement = final["refinement"]
    assert refinement["parent_job_id"] == parent_id
    diff = refinement["diff"]
    assert diff["summary"]["modified"] >= 1
    ops = diff["operations"]
    todo_mod = next(op for op in ops if op["kind"] == "entity" and op["label"] == "Todo")
    assert todo_mod["type"] == "modified"
    after_fields = {f["name"] for f in todo_mod["after"]["fields"]}
    assert "priority" in after_fields


def test_refine_404_when_parent_missing(client: TestClient):
    res = client.post(
        "/jobs/nope/refine",
        json={"user_message": "x", "provider": "anthropic", "model": "claude-opus-4-7"},
        headers={"X-Provider-Key": "test-key"},
    )
    assert res.status_code == 404


def test_refine_409_when_parent_has_no_spec(client: TestClient):
    parent = jobs_module._new_job("waiting")
    jobs_module._jobs["waiting"] = parent
    res = client.post(
        "/jobs/waiting/refine",
        json={"user_message": "x", "provider": "anthropic", "model": "claude-opus-4-7"},
        headers={"X-Provider-Key": "test-key"},
    )
    assert res.status_code == 409


def test_refine_400_on_unsupported_provider(client: TestClient):
    parent_id = _seed_parent()
    res = client.post(
        f"/jobs/{parent_id}/refine",
        json={"user_message": "x", "provider": "cohere", "model": "command-r"},
        headers={"X-Provider-Key": "k"},
    )
    assert res.status_code == 400


def test_refine_422_on_empty_user_message(client: TestClient):
    parent_id = _seed_parent()
    res = client.post(
        f"/jobs/{parent_id}/refine",
        json={"user_message": "", "provider": "anthropic", "model": "claude-opus-4-7"},
        headers={"X-Provider-Key": "k"},
    )
    assert res.status_code == 422


def test_refine_propagates_max_tokens_budget(client: TestClient):
    parent_id = _seed_parent()
    res = client.post(
        f"/jobs/{parent_id}/refine",
        json={
            "user_message": "Add x",
            "provider": "anthropic",
            "model": "claude-opus-4-7",
            "max_tokens": 100,
        },
        headers={"X-Provider-Key": "k"},
    )
    assert res.status_code == 200
    final = _wait_done(client, res.json()["id"])
    assert final["status"] == "failed"
    assert "budget" in (final["error"] or "").lower()


def test_refine_child_independent_of_parent(client: TestClient):
    parent_id = _seed_parent()
    res = client.post(
        f"/jobs/{parent_id}/refine",
        json={
            "user_message": "Add priority field",
            "provider": "anthropic",
            "model": "claude-opus-4-7",
        },
        headers={"X-Provider-Key": "k"},
    )
    child_id = res.json()["id"]
    _wait_done(client, child_id)

    parent_body = client.get(f"/jobs/{parent_id}").json()
    child_body = client.get(f"/jobs/{child_id}").json()
    assert parent_body["spec"] == _todo_spec()
    assert child_body["spec"] != _todo_spec()
    assert parent_body.get("refinement") is None
    assert child_body["refinement"]["parent_job_id"] == parent_id
