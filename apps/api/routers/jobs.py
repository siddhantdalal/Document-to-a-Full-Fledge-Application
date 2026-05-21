from uuid import uuid4

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile

router = APIRouter(prefix="/jobs")


@router.post("")
async def create_job(
    doc: UploadFile = File(...),
    provider: str = Form(...),
    model: str = Form(...),
    x_provider_key: str = Header(..., alias="X-Provider-Key"),
) -> dict[str, str]:
    if not x_provider_key:
        raise HTTPException(status_code=400, detail="Missing provider key.")
    return {"job_id": uuid4().hex, "status": "pending"}


@router.get("/{job_id}")
def get_job(job_id: str) -> dict[str, str]:
    return {"job_id": job_id, "status": "pending"}


@router.get("/{job_id}/artifact")
def get_artifact(job_id: str) -> dict[str, str]:
    raise HTTPException(status_code=501, detail="Not implemented.")
