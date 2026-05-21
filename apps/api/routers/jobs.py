import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse

from packages.ai_providers.anthropic_client import AnthropicClient
from packages.generator import generate, package_zip
from packages.spec_extractor import extract_spec

router = APIRouter(prefix="/jobs")

_jobs: dict[str, dict[str, Any]] = {}
_ARTIFACT_ROOT = Path(tempfile.gettempdir()) / "doc-to-app-artifacts"


def _run_pipeline(job_id: str, markdown: str, key: str, model: str) -> None:
    job = _jobs[job_id]
    job["status"] = "running"
    try:
        llm = AnthropicClient(api_key=key, model=model)
        spec = extract_spec(markdown, llm)
        job["spec"] = spec
        work_dir = _ARTIFACT_ROOT / job_id
        project = generate(spec, work_dir / "project")
        job["artifact_path"] = str(package_zip(project, work_dir / f"{job_id}.zip"))
        job["status"] = "succeeded"
    except Exception as exc:
        job["error"] = str(exc)
        job["status"] = "failed"


@router.post("")
async def create_job(
    background: BackgroundTasks,
    doc: UploadFile = File(...),
    provider: str = Form(...),
    model: str = Form(...),
    x_provider_key: str = Header(..., alias="X-Provider-Key"),
) -> dict[str, str]:
    if provider != "anthropic":
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
    content = (await doc.read()).decode("utf-8", errors="replace")
    job_id = uuid4().hex
    _jobs[job_id] = {
        "id": job_id,
        "status": "pending",
        "spec": None,
        "error": None,
        "artifact_path": None,
    }
    background.add_task(_run_pipeline, job_id, content, x_provider_key, model)
    return {"job_id": job_id, "status": "pending"}


@router.get("/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {k: v for k, v in _jobs[job_id].items() if k != "artifact_path"}


@router.get("/{job_id}/artifact")
def get_artifact(job_id: str) -> FileResponse:
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job["status"] != "succeeded":
        raise HTTPException(status_code=409, detail=f"Job status is {job['status']}.")
    return FileResponse(
        job["artifact_path"], filename=f"{job_id}.zip", media_type="application/zip"
    )
