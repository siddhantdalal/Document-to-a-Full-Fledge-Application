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

from packages.ai_providers.anthropic_client import AnthropicClient
from packages.spec_extractor import extract_spec

router = APIRouter(prefix="/jobs")

_jobs: dict[str, dict[str, Any]] = {}


def _run_extraction(job_id: str, markdown: str, key: str, model: str) -> None:
    _jobs[job_id]["status"] = "running"
    try:
        llm = AnthropicClient(api_key=key, model=model)
        _jobs[job_id]["spec"] = extract_spec(markdown, llm)
        _jobs[job_id]["status"] = "succeeded"
    except Exception as exc:
        _jobs[job_id]["error"] = str(exc)
        _jobs[job_id]["status"] = "failed"


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
    _jobs[job_id] = {"id": job_id, "status": "pending", "spec": None, "error": None}
    background.add_task(_run_extraction, job_id, content, x_provider_key, model)
    return {"job_id": job_id, "status": "pending"}


@router.get("/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found.")
    return _jobs[job_id]


@router.get("/{job_id}/artifact")
def get_artifact(job_id: str) -> dict[str, str]:
    raise HTTPException(status_code=501, detail="Not implemented.")
