import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.auth.deps import CurrentBusiness, Db
from app.jobs import queue

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class JobOut(BaseModel):
    id: int
    kind: str
    status: str
    attempts: int
    error: str | None


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: int, conn: Db, business_id: CurrentBusiness):  # type: ignore[no-untyped-def]
    job = queue.get_job(conn, job_id)
    # jobs carry business_id in their payload; hide other tenants' jobs.
    if job is None or json.loads(job["payload_json"]).get("business_id") != business_id:
        raise HTTPException(status_code=404, detail="Job not found")
    return dict(job)
