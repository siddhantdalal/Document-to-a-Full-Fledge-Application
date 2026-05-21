from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException

from apps.api.routers import jobs as jobs_module
from packages.runner import (
    Preview,
    PreviewError,
    check_docker,
    fetch_logs,
    start_preview,
    stop_preview,
)

router = APIRouter(prefix="/jobs")

_previews: dict[str, Preview] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _public(preview: Preview, status: str = "running", error: str | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "frontend_url": preview.frontend_url,
        "backend_url": preview.backend_url,
        "started_at": preview.started_at,
        "error": error,
    }


def _starting_view() -> dict[str, Any]:
    return {
        "status": "starting",
        "frontend_url": None,
        "backend_url": None,
        "started_at": _now(),
        "error": None,
    }


def _failed_view(message: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "frontend_url": None,
        "backend_url": None,
        "started_at": None,
        "error": message,
    }


def _stop_all_previews() -> None:
    for job_id, preview in list(_previews.items()):
        try:
            stop_preview(preview)
        except Exception:
            pass
        _previews.pop(job_id, None)
        if job_id in jobs_module._jobs:
            jobs_module._jobs[job_id]["preview"] = None


def _start_preview_async(job_id: str) -> None:
    job = jobs_module._jobs.get(job_id)
    if not job:
        return
    try:
        preview = start_preview(job_id, jobs_module.project_dir_for(job_id))
        _previews[job_id] = preview
        job["preview"] = _public(preview)
    except PreviewError as exc:
        job["preview"] = _failed_view(str(exc))
    except Exception as exc:
        job["preview"] = _failed_view(f"unexpected error: {exc}")


@router.post("/{job_id}/preview/start")
def start(job_id: str, background: BackgroundTasks) -> dict[str, Any]:
    job = jobs_module._jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if not job["artifact_ready"]:
        raise HTTPException(status_code=409, detail="Job has no artifact yet.")

    docker_error = check_docker()
    if docker_error:
        raise HTTPException(status_code=503, detail=f"Preview unavailable: {docker_error}")

    existing = _previews.get(job_id)
    if existing and (job.get("preview") or {}).get("status") == "running":
        return _public(existing)

    _stop_all_previews()
    job["preview"] = _starting_view()
    background.add_task(_start_preview_async, job_id)
    return job["preview"]


@router.post("/{job_id}/preview/stop")
def stop(job_id: str) -> dict[str, str]:
    preview = _previews.pop(job_id, None)
    if preview:
        try:
            stop_preview(preview)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"stop failed: {exc}") from exc
    if job_id in jobs_module._jobs:
        jobs_module._jobs[job_id]["preview"] = None
    return {"status": "stopped"}


@router.get("/{job_id}/preview/logs")
def logs(job_id: str, tail: int = 200) -> dict[str, list[str] | str]:
    preview = _previews.get(job_id)
    if not preview:
        raise HTTPException(status_code=404, detail="No active preview for this job.")
    return {"lines": fetch_logs(preview, tail=tail)}
