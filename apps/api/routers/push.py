from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.api.routers import jobs as jobs_module
from packages.publisher import PushError, push_to_github

router = APIRouter(prefix="/jobs")


class PushRequest(BaseModel):
    token: str = Field(..., min_length=1, description="GitHub Personal Access Token")
    owner: str = Field(..., min_length=1, max_length=39)
    repo: str = Field(..., min_length=1, max_length=100)
    private: bool = True
    commit_message: str | None = None


@router.post("/{job_id}/push")
def push(job_id: str, request: PushRequest) -> dict[str, Any]:
    job = jobs_module._jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if not job["artifact_ready"]:
        raise HTTPException(status_code=409, detail="Job has no artifact yet.")

    spec_name = (job.get("spec") or {}).get("app", {}).get("name") or "generated app"
    message = request.commit_message or f"Generate {spec_name}"

    try:
        result = push_to_github(
            project_dir=jobs_module.project_dir_for(job_id),
            token=request.token,
            owner=request.owner,
            repo=request.repo,
            private=request.private,
            commit_message=message,
        )
    except PushError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "repo_url": result.repo_url,
        "branch": result.branch,
        "commit_sha": result.commit_sha,
    }
