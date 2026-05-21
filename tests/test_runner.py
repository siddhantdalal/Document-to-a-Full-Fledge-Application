import subprocess
from pathlib import Path

import pytest

from packages import runner


class FakeRun:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self._scripted: list[subprocess.CompletedProcess] = []

    def script(self, *results: subprocess.CompletedProcess) -> None:
        self._scripted.extend(results)

    def __call__(self, cmd, **kwargs) -> subprocess.CompletedProcess:
        self.calls.append(list(cmd))
        if self._scripted:
            return self._scripted.pop(0)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


@pytest.fixture
def fake_run(monkeypatch: pytest.MonkeyPatch) -> FakeRun:
    fake = FakeRun()
    monkeypatch.setattr(runner.subprocess, "run", fake)
    return fake


def _make_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / "backend").mkdir(parents=True)
    (project / "backend" / "Dockerfile").write_text("FROM scratch\n")
    (project / "frontend").mkdir()
    (project / "frontend" / "Dockerfile").write_text("FROM scratch\n")
    return project


def test_check_docker_returns_none_when_compose_available(fake_run: FakeRun):
    fake_run.script(subprocess.CompletedProcess([], 0, stdout="Docker Compose version v2.30.0"))
    assert runner.check_docker() is None


def test_check_docker_returns_error_on_failure(fake_run: FakeRun):
    fake_run.script(subprocess.CompletedProcess([], 1, stdout="", stderr="not found"))
    assert runner.check_docker() == "not found"


def test_check_docker_returns_error_when_cli_missing(monkeypatch):
    def raise_fnf(*a, **kw):
        raise FileNotFoundError("no docker")

    monkeypatch.setattr(runner.subprocess, "run", raise_fnf)
    assert runner.check_docker() == "docker CLI not found"


def test_write_preview_compose_emits_expected_yaml(tmp_path: Path):
    project = _make_project(tmp_path)
    path = runner.write_preview_compose(project, backend_port=18001, frontend_port=15174)
    assert path.exists()
    text = path.read_text()
    assert '"18001:8000"' in text
    assert '"15174:5173"' in text
    assert "VITE_API_URL: http://localhost:18001" in text


def test_start_preview_runs_compose_up_with_expected_args(tmp_path: Path, fake_run: FakeRun):
    project = _make_project(tmp_path)
    preview = runner.start_preview("abcdef1234567890", project)
    assert preview.backend_port == runner.PREVIEW_BACKEND_PORT
    assert preview.frontend_port == runner.PREVIEW_FRONTEND_PORT
    assert preview.project_name == "doc-to-app-abcdef123456"
    assert preview.backend_url == f"http://localhost:{runner.PREVIEW_BACKEND_PORT}"
    assert preview.frontend_url == f"http://localhost:{runner.PREVIEW_FRONTEND_PORT}"

    cmd = fake_run.calls[0]
    assert cmd[:2] == ["docker", "compose"]
    assert "-p" in cmd and "doc-to-app-abcdef123456" in cmd
    assert cmd[-3:] == ["up", "-d", "--build"]
    assert str(preview.compose_file) in cmd


def test_start_preview_raises_when_dockerfile_missing(tmp_path: Path):
    project = tmp_path / "empty"
    project.mkdir()
    with pytest.raises(runner.PreviewError) as exc:
        runner.start_preview("x" * 16, project)
    assert "Dockerfile not found" in str(exc.value)


def test_start_preview_raises_when_compose_fails(tmp_path: Path, fake_run: FakeRun):
    project = _make_project(tmp_path)
    fake_run.script(
        subprocess.CompletedProcess([], 1, stdout="", stderr="port already in use")
    )
    with pytest.raises(runner.PreviewError) as exc:
        runner.start_preview("abcdef1234567890", project)
    assert "port already in use" in str(exc.value)


def test_stop_preview_invokes_compose_down(tmp_path: Path, fake_run: FakeRun):
    project = _make_project(tmp_path)
    preview = runner.start_preview("abcdef1234567890", project)
    fake_run.calls.clear()
    runner.stop_preview(preview)
    cmd = fake_run.calls[0]
    assert cmd[-3:] == ["down", "-v", "--remove-orphans"]
    assert "doc-to-app-abcdef123456" in cmd


def test_fetch_logs_returns_lines(tmp_path: Path, fake_run: FakeRun):
    project = _make_project(tmp_path)
    preview = runner.start_preview("abcdef1234567890", project)
    fake_run.script(
        subprocess.CompletedProcess([], 0, stdout="backend | line 1\nfrontend | line 2\n")
    )
    out = runner.fetch_logs(preview, tail=50)
    assert out == ["backend | line 1", "frontend | line 2"]
    cmd = fake_run.calls[-1]
    assert "logs" in cmd and "--tail" in cmd and "50" in cmd


def test_fetch_logs_returns_error_marker_on_failure(tmp_path: Path, fake_run: FakeRun):
    project = _make_project(tmp_path)
    preview = runner.start_preview("abcdef1234567890", project)
    fake_run.script(subprocess.CompletedProcess([], 1, stdout="", stderr="no such project"))
    out = runner.fetch_logs(preview)
    assert out[0].startswith("[error]")
    assert "no such project" in out[0]
