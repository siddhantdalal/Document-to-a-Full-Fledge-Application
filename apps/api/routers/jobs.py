import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
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
from packages.ai_providers.base import LLMClient
from packages.ai_providers.openai_client import OpenAIClient
from packages.doc_parser import DocParseError, parse as parse_doc
from packages.generator import generate, package_zip
from packages.generator.template import slugify
from packages.reconciler import reconcile
from packages.spec_extractor import extract_spec
from packages.validator import validate

SUPPORTED_PROVIDERS = ("anthropic", "openai")


def _make_client(provider: str, key: str, model: str) -> LLMClient:
    if provider == "anthropic":
        return AnthropicClient(api_key=key, model=model)
    if provider == "openai":
        return OpenAIClient(api_key=key, model=model)
    raise ValueError(f"Unsupported provider: {provider}")

router = APIRouter(prefix="/jobs")

STAGE_NAMES = ("extract_spec", "generate", "validate", "reconcile", "package")

_jobs: dict[str, dict[str, Any]] = {}
_ARTIFACT_ROOT = Path(tempfile.gettempdir()) / "doc-to-app-artifacts"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_job(job_id: str) -> dict[str, Any]:
    return {
        "id": job_id,
        "status": "pending",
        "stages": [
            {
                "name": name,
                "status": "pending",
                "started_at": None,
                "finished_at": None,
                "message": None,
            }
            for name in STAGE_NAMES
        ],
        "spec": None,
        "validation": None,
        "reconciliation": None,
        "error": None,
        "artifact_ready": False,
        "artifact_path": None,
        "created_at": _now(),
        "updated_at": _now(),
    }


def _stage(job: dict[str, Any], name: str) -> dict[str, Any]:
    return next(s for s in job["stages"] if s["name"] == name)


def _start_stage(job: dict[str, Any], name: str) -> None:
    stage = _stage(job, name)
    stage["status"] = "running"
    stage["started_at"] = _now()
    job["updated_at"] = _now()


def _finish_stage(job: dict[str, Any], name: str, message: str | None = None) -> None:
    stage = _stage(job, name)
    stage["status"] = "succeeded"
    stage["finished_at"] = _now()
    if message:
        stage["message"] = message
    job["updated_at"] = _now()


def _fail_stage(job: dict[str, Any], name: str, message: str) -> None:
    stage = _stage(job, name)
    stage["status"] = "failed"
    stage["finished_at"] = _now()
    stage["message"] = message
    job["updated_at"] = _now()


def _run_pipeline(job_id: str, markdown: str, provider: str, key: str, model: str) -> None:
    job = _jobs[job_id]
    job["status"] = "running"
    job["updated_at"] = _now()
    try:
        _start_stage(job, "extract_spec")
        llm = _make_client(provider, key, model)
        spec = extract_spec(markdown, llm)
        job["spec"] = spec
        _finish_stage(
            job,
            "extract_spec",
            (
                f"{len(spec.get('entities', []))} entities · "
                f"{len(spec.get('endpoints', []))} endpoints · "
                f"{len(spec.get('screens', []))} screens"
            ),
        )

        _start_stage(job, "generate")
        work_dir = _ARTIFACT_ROOT / job_id
        project = generate(spec, work_dir / "project")
        file_count = sum(1 for _ in project.rglob("*") if _.is_file())
        _finish_stage(job, "generate", f"{file_count} files written")

        _start_stage(job, "validate")
        v = validate(project)
        job["validation"] = asdict(v)
        if not v.ok:
            _fail_stage(job, "validate", f"{len(v.errors)} compile error(s)")
            job["error"] = "\n".join(v.errors[:5])
            job["status"] = "failed"
            job["updated_at"] = _now()
            return
        _finish_stage(
            job,
            "validate",
            f"{v.summary.get('python_files', 0)} Python files compiled cleanly",
        )

        _start_stage(job, "reconcile")
        r = reconcile(spec, project)
        job["reconciliation"] = asdict(r)
        total = sum(c["total"] for c in r.coverage.values())
        covered = sum(c["covered"] for c in r.coverage.values())
        if r.missing:
            _fail_stage(job, "reconcile", f"{len(r.missing)} spec item(s) not implemented")
            job["error"] = "Spec coverage gaps:\n" + "\n".join(r.missing[:5])
            job["status"] = "failed"
            job["updated_at"] = _now()
            return
        extras = f" ({len(r.extra)} extra)" if r.extra else ""
        _finish_stage(job, "reconcile", f"{covered}/{total} spec items covered{extras}")

        _start_stage(job, "package")
        zip_path = package_zip(project, work_dir / f"{job_id}.zip")
        job["artifact_path"] = str(zip_path)
        job["artifact_ready"] = True
        size_kb = max(1, zip_path.stat().st_size // 1024)
        _finish_stage(job, "package", f"{size_kb} KB archive")

        job["status"] = "succeeded"
    except Exception as exc:
        running = next((s for s in job["stages"] if s["status"] == "running"), None)
        if running:
            _fail_stage(job, running["name"], str(exc))
        job["error"] = str(exc)
        job["status"] = "failed"
    job["updated_at"] = _now()


def _public(job: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in job.items() if k != "artifact_path"}


@router.post("")
async def create_job(
    background: BackgroundTasks,
    doc: UploadFile = File(...),
    provider: str = Form(...),
    model: str = Form(...),
    x_provider_key: str = Header(..., alias="X-Provider-Key"),
) -> dict[str, Any]:
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
    raw = await doc.read()
    try:
        content = parse_doc(raw, doc.filename or "uploaded.md")
    except DocParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not content.strip():
        raise HTTPException(status_code=400, detail="Document is empty.")
    job_id = uuid4().hex
    _jobs[job_id] = _new_job(job_id)
    background.add_task(_run_pipeline, job_id, content, provider, x_provider_key, model)
    return _public(_jobs[job_id])


@router.get("/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found.")
    return _public(_jobs[job_id])


@router.get("/{job_id}/artifact")
def get_artifact(job_id: str) -> FileResponse:
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if not job["artifact_ready"]:
        raise HTTPException(status_code=409, detail=f"Job status is {job['status']}.")
    name = job.get("spec", {}).get("app", {}).get("name") if job.get("spec") else job_id
    return FileResponse(
        job["artifact_path"],
        filename=f"{slugify(name or job_id)}.zip",
        media_type="application/zip",
    )
