import re
import subprocess
import textwrap
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PREVIEW_BACKEND_PORT = 18000
PREVIEW_FRONTEND_PORT = 15173

_COMPOSE_FILENAME = "compose.preview.yml"
_PORT_RE = re.compile(r"(?:0\.0\.0\.0|\[::\]|127\.0\.0\.1):(\d+)")


class PreviewError(Exception):
    pass


@dataclass
class Preview:
    job_id: str
    project_dir: Path
    project_name: str
    compose_file: Path
    backend_port: int
    frontend_port: int
    started_at: str

    @property
    def backend_url(self) -> str:
        return f"http://localhost:{self.backend_port}"

    @property
    def frontend_url(self) -> str:
        return f"http://localhost:{self.frontend_port}"


def check_docker() -> str | None:
    try:
        result = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return (result.stderr or "docker compose check failed").strip()
    except FileNotFoundError:
        return "docker CLI not found"
    except subprocess.TimeoutExpired:
        return "docker check timed out"
    return None


def write_preview_compose(
    project_dir: Path,
    backend_port: int = PREVIEW_BACKEND_PORT,
    frontend_port: int = PREVIEW_FRONTEND_PORT,
) -> Path:
    content = textwrap.dedent(
        f"""\
        services:
          backend:
            build: ./backend
            ports:
              - "{backend_port}:8000"
          frontend:
            build: ./frontend
            ports:
              - "{frontend_port}:5173"
            environment:
              VITE_API_URL: http://localhost:{backend_port}
            depends_on:
              - backend
        """
    )
    path = project_dir / _COMPOSE_FILENAME
    path.write_text(content)
    return path


def _compose(preview: Preview, *extra: str) -> list[str]:
    return [
        "docker",
        "compose",
        "-p",
        preview.project_name,
        "-f",
        str(preview.compose_file),
        *extra,
    ]


def _project_name(job_id: str) -> str:
    return f"doc-to-app-{job_id[:12]}"


def start_preview(
    job_id: str,
    project_dir: Path,
    backend_port: int = PREVIEW_BACKEND_PORT,
    frontend_port: int = PREVIEW_FRONTEND_PORT,
) -> Preview:
    project_dir = Path(project_dir)
    if not (project_dir / "backend" / "Dockerfile").exists():
        raise PreviewError(f"backend/Dockerfile not found under {project_dir}")
    if not (project_dir / "frontend" / "Dockerfile").exists():
        raise PreviewError(f"frontend/Dockerfile not found under {project_dir}")

    compose_file = write_preview_compose(project_dir, backend_port, frontend_port)
    project_name = _project_name(job_id)
    cmd = [
        "docker",
        "compose",
        "-p",
        project_name,
        "-f",
        str(compose_file),
        "up",
        "-d",
        "--build",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()[:800]
        raise PreviewError(f"docker compose up failed: {message}")

    return Preview(
        job_id=job_id,
        project_dir=project_dir,
        project_name=project_name,
        compose_file=compose_file,
        backend_port=backend_port,
        frontend_port=frontend_port,
        started_at=datetime.now(timezone.utc).isoformat(),
    )


def stop_preview(preview: Preview) -> None:
    cmd = _compose(preview, "down", "-v", "--remove-orphans")
    subprocess.run(cmd, capture_output=True, text=True, timeout=120)


def fetch_logs(preview: Preview, tail: int = 200) -> list[str]:
    cmd = _compose(
        preview,
        "logs",
        "--tail",
        str(tail),
        "--no-color",
        "--timestamps",
    )
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        return [f"[error] {(result.stderr or result.stdout or '').strip()}"]
    return result.stdout.splitlines()


__all__ = [
    "PREVIEW_BACKEND_PORT",
    "PREVIEW_FRONTEND_PORT",
    "Preview",
    "PreviewError",
    "check_docker",
    "fetch_logs",
    "start_preview",
    "stop_preview",
    "write_preview_compose",
]
