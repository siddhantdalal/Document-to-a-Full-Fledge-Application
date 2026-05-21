import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from packages import publisher
from packages.publisher import PushError, push_to_github


def _make_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "README.md").write_text("# Generated\n")
    (project / "backend").mkdir()
    (project / "backend" / "main.py").write_text("print('hi')\n")
    return project


def _http_response(status: int, body: dict | None = None) -> httpx.Response:
    return httpx.Response(status_code=status, json=body or {})


class FakeGit:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self._scripted: list[subprocess.CompletedProcess] = []

    def script_default_success(self) -> None:
        # init, config email, config name, add, commit, push, rev-parse
        self._scripted = [
            subprocess.CompletedProcess([], 0),
            subprocess.CompletedProcess([], 0),
            subprocess.CompletedProcess([], 0),
            subprocess.CompletedProcess([], 0),
            subprocess.CompletedProcess([], 0),
            subprocess.CompletedProcess([], 0),
            subprocess.CompletedProcess([], 0, stdout="deadbeef\n"),
        ]

    def __call__(self, cmd, **kwargs) -> subprocess.CompletedProcess:
        self.calls.append(list(cmd))
        if self._scripted:
            return self._scripted.pop(0)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


@pytest.fixture
def fake_git(monkeypatch: pytest.MonkeyPatch) -> FakeGit:
    fake = FakeGit()
    monkeypatch.setattr(publisher.subprocess, "run", fake)
    return fake


@pytest.fixture
def fake_gh(monkeypatch: pytest.MonkeyPatch):
    calls: list[dict] = []

    def fake_request(method: str, url: str, headers=None, json=None, timeout=None):
        calls.append({"method": method, "url": url, "headers": headers, "json": json})
        if url.endswith("/user"):
            return _http_response(200, {"login": "siddhantdalal"})
        if url.endswith("/repos/siddhantdalal/todo-app"):
            return _http_response(404)
        if url.endswith("/user/repos") and method == "POST":
            return _http_response(201, {"clone_url": "https://github.com/siddhantdalal/todo-app.git"})
        return _http_response(404)

    monkeypatch.setattr(httpx, "request", fake_request)
    return calls


def test_push_to_github_creates_repo_and_pushes(tmp_path, fake_git, fake_gh):
    project = _make_project(tmp_path)
    fake_git.script_default_success()

    result = push_to_github(
        project_dir=project,
        token="ghp_TESTTOKEN",
        owner="siddhantdalal",
        repo="todo-app",
        private=True,
        commit_message="Generate Todo App",
    )

    assert result.repo_url == "https://github.com/siddhantdalal/todo-app"
    assert result.branch == "main"
    assert result.commit_sha == "deadbeef"

    methods = [(c["method"], c["url"]) for c in fake_gh]
    assert ("GET", f"{publisher.GITHUB_API}/user") in methods
    assert ("GET", f"{publisher.GITHUB_API}/repos/siddhantdalal/todo-app") in methods
    create_call = next(c for c in fake_gh if c["method"] == "POST")
    assert create_call["url"] == f"{publisher.GITHUB_API}/user/repos"
    assert create_call["json"] == {"name": "todo-app", "private": True, "auto_init": False}
    assert create_call["headers"]["Authorization"] == "Bearer ghp_TESTTOKEN"

    git_commands = [c[1] for c in fake_git.calls]
    assert "init" in git_commands
    assert "add" in git_commands
    assert "push" in fake_git.calls[-2]
    assert fake_git.calls[-1][:2] == ["git", "rev-parse"]
    push_cmd = next(c for c in fake_git.calls if "push" in c)
    assert any("x-access-token:ghp_TESTTOKEN@github.com" in arg for arg in push_cmd)


def test_push_to_github_rejects_existing_repo(tmp_path, fake_git, monkeypatch):
    project = _make_project(tmp_path)

    def fake_request(method, url, **kwargs):
        if url.endswith("/user"):
            return _http_response(200, {"login": "siddhantdalal"})
        if url.endswith("/repos/siddhantdalal/todo-app"):
            return _http_response(200, {})
        return _http_response(404)

    monkeypatch.setattr(httpx, "request", fake_request)

    with pytest.raises(PushError) as exc:
        push_to_github(
            project_dir=project,
            token="ghp_TOKEN",
            owner="siddhantdalal",
            repo="todo-app",
        )
    assert "already exists" in str(exc.value)


def test_push_to_github_rejects_bad_token(tmp_path, fake_git, monkeypatch):
    project = _make_project(tmp_path)

    def fake_request(method, url, **kwargs):
        return _http_response(401)

    monkeypatch.setattr(httpx, "request", fake_request)

    with pytest.raises(PushError) as exc:
        push_to_github(
            project_dir=project,
            token="bad",
            owner="siddhantdalal",
            repo="todo-app",
        )
    assert "rejected" in str(exc.value)


def test_push_to_github_redacts_token_in_error(tmp_path, monkeypatch, fake_gh):
    project = _make_project(tmp_path)

    def boom(*args, **kwargs):
        return subprocess.CompletedProcess([], 1, stderr="error pushing to https://x-access-token:ghp_TESTTOKEN@github.com")

    monkeypatch.setattr(publisher.subprocess, "run", boom)

    with pytest.raises(PushError) as exc:
        push_to_github(
            project_dir=project,
            token="ghp_TESTTOKEN",
            owner="siddhantdalal",
            repo="todo-app",
        )
    assert "ghp_TESTTOKEN" not in str(exc.value)
    assert "***" in str(exc.value)


def test_push_to_github_rejects_invalid_repo_name(tmp_path, fake_git):
    project = _make_project(tmp_path)
    with pytest.raises(PushError) as exc:
        push_to_github(
            project_dir=project,
            token="ghp_TOKEN",
            owner="siddhantdalal",
            repo="bad name with spaces",
        )
    assert "must contain only" in str(exc.value)


def test_push_to_github_requires_generated_project(tmp_path, fake_git):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(PushError) as exc:
        push_to_github(
            project_dir=empty,
            token="ghp_TOKEN",
            owner="siddhantdalal",
            repo="todo-app",
        )
    assert "README.md" in str(exc.value)
