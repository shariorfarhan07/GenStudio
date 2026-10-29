import copy
import json
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.jobs.models import Job
from app.jobs.queue import cancel_job, enqueue, get_session, reorder_queue
from app.pipelines.registry import pipeline_registry

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class CreateJobRequest(BaseModel):
    pipeline_id: str
    params: dict
    batch: Optional[dict] = None   # {mode: "variations"|"prompt_list"|"folder", count?, prompts?, folder?}


class ReorderRequest(BaseModel):
    ordered_ids: list[str]


@router.post("")
async def create_jobs(req: CreateJobRequest):
    manifest = pipeline_registry.get(req.pipeline_id)
    if not manifest:
        raise HTTPException(404, f"Pipeline not found: {req.pipeline_id}")

    ok, reason = pipeline_registry.is_available(req.pipeline_id)
    if not ok:
        raise HTTPException(422, f"Pipeline not available: {reason}")

    created: list[str] = []
    batch = req.batch or {}
    mode = batch.get("mode", "single")

    if mode == "single" or not batch:
        job = Job(
            pipeline_id=req.pipeline_id,
            task=manifest.task,
            params_json=json.dumps(req.params),
        )
        enqueue(job)
        created.append(job.id)

    elif mode == "variations":
        count = int(batch.get("count", 4))
        batch_id = str(uuid.uuid4())
        for _ in range(count):
            p = copy.deepcopy(req.params)
            p["seed"] = -1  # randomize each
            job = Job(
                pipeline_id=req.pipeline_id,
                task=manifest.task,
                params_json=json.dumps(p),
                batch_id=batch_id,
            )
            enqueue(job)
            created.append(job.id)

    elif mode == "prompt_list":
        prompts: list[str] = batch.get("prompts", [])
        batch_id = str(uuid.uuid4())
        for prompt in prompts:
            p = copy.deepcopy(req.params)
            p["prompt"] = prompt
            job = Job(
                pipeline_id=req.pipeline_id,
                task=manifest.task,
                params_json=json.dumps(p),
                batch_id=batch_id,
            )
            enqueue(job)
            created.append(job.id)

    return {"job_ids": created}


@router.get("")
async def list_jobs(status: Optional[str] = None, limit: int = 50):
    with get_session() as s:
        stmt = select(Job).order_by(Job.priority.desc(), Job.created_at)
        if status:
            stmt = stmt.where(Job.status == status)
        stmt = stmt.limit(limit)
        jobs = s.exec(stmt).all()
        return [_job_dict(j) for j in jobs]


@router.get("/{job_id}")
async def get_job(job_id: str):
    with get_session() as s:
        job = s.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        return _job_dict(job)


@router.post("/{job_id}/cancel")
async def cancel(job_id: str):
    ok = cancel_job(job_id)
    if not ok:
        raise HTTPException(404, "Job not found or cannot be cancelled")
    return {"ok": True}


@router.post("/{job_id}/retry")
async def retry(job_id: str):
    with get_session() as s:
        job = s.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        if job.status not in ("failed", "cancelled"):
            raise HTTPException(400, "Job is not failed or cancelled")
        job.status = "queued"
        job.error = None
        job.progress = 0
        job.attempts = 0
        job.started_at = None
        job.finished_at = None
        s.add(job)
        s.commit()
    return {"ok": True}


@router.patch("/order")
async def reorder(req: ReorderRequest):
    reorder_queue(req.ordered_ids)
    return {"ok": True}


def _job_dict(job: Job) -> dict:
    return {
        "id": job.id,
        "batch_id": job.batch_id,
        "pipeline_id": job.pipeline_id,
        "task": job.task,
        "status": job.status,
        "progress": job.progress,
        "eta_seconds": job.eta_seconds,
        "error": job.error,
        "attempts": job.attempts,
        "priority": job.priority,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }
