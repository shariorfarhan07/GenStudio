"""
Job scheduler — one job runs at a time, persistent across restarts via SQLite.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from app.config import get_settings
from app.engine.client import ExecutionInterrupted, comfy_client
from app.engine.process import engine_process
from app.jobs.events import broadcast
from app.jobs.models import Asset, Job
from app.media.store import save_job_outputs

logger = logging.getLogger(__name__)

_scheduler_task: Optional[asyncio.Task] = None
_current_job_id: Optional[str] = None
_db_engine = None   # set by main.py


def set_db_engine(engine) -> None:
    global _db_engine
    _db_engine = engine


def get_session() -> Session:
    return Session(_db_engine, expire_on_commit=False)


# ── Public API ────────────────────────────────────────────────────────────

def enqueue(job: Job) -> None:
    with get_session() as s:
        s.add(job)
        s.commit()
    broadcast("job_queued", {"id": job.id, "status": job.status})


def cancel_job(job_id: str) -> bool:
    with get_session() as s:
        job = s.get(Job, job_id)
        if not job:
            return False
        if job.status == "running":
            asyncio.create_task(comfy_client.interrupt())
        if job.status in ("queued", "preparing", "running"):
            job.status = "cancelled"
            job.finished_at = datetime.now(timezone.utc)
            s.add(job)
            s.commit()
            broadcast("job_updated", {"id": job_id, "status": "cancelled"})
            return True
    return False


def reorder_queue(ordered_ids: list[str]) -> None:
    with get_session() as s:
        for priority, jid in enumerate(reversed(ordered_ids)):
            job = s.get(Job, jid)
            if job and job.status == "queued":
                job.priority = priority
                s.add(job)
        s.commit()


# ── Scheduler loop ────────────────────────────────────────────────────────

def recover_interrupted_jobs() -> int:
    """Reset jobs left mid-flight by a crash back to queued."""
    n = 0
    with get_session() as s:
        stuck = s.exec(
            select(Job).where(Job.status.in_(("preparing", "running", "postprocessing")))
        ).all()
        for job in stuck:
            job.status = "queued"
            job.progress = 0
            job.started_at = None
            s.add(job)
            n += 1
        s.commit()
    if n:
        logger.info("Recovered %d interrupted job(s)", n)
    return n


async def start_scheduler() -> None:
    global _scheduler_task
    recover_interrupted_jobs()
    _scheduler_task = asyncio.create_task(_scheduler_loop(), name="job-scheduler")


async def stop_scheduler() -> None:
    if _scheduler_task:
        _scheduler_task.cancel()


async def _scheduler_loop() -> None:
    logger.info("Job scheduler started")
    while True:
        try:
            await _process_next()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Scheduler error: %s", e, exc_info=True)
        await asyncio.sleep(1.0)


async def _process_next() -> None:
    global _current_job_id

    # Pick the highest-priority queued job
    with get_session() as s:
        stmt = (
            select(Job)
            .where(Job.status == "queued")
            .order_by(Job.priority.desc(), Job.created_at)
            .limit(1)
        )
        job = s.exec(stmt).first()
        if not job:
            return
        job_id = job.id

    if engine_process.status not in ("ready", "busy"):
        logger.debug("Engine not ready (%s), waiting…", engine_process.status)
        return

    _current_job_id = job_id
    await _run_job(job_id)
    _current_job_id = None


async def _run_job(job_id: str) -> None:
    from app.pipelines.patcher import patch_workflow
    from app.pipelines.registry import pipeline_registry

    with get_session() as s:
        job = s.get(Job, job_id)
        if not job or job.status != "queued":
            return
        job.status = "preparing"
        job.started_at = datetime.now(timezone.utc)
        job.attempts += 1
        s.add(job)
        s.commit()
        params = json.loads(job.params_json)
        pipeline_id = job.pipeline_id

    broadcast("job_updated", {"id": job_id, "status": "preparing"})

    manifest = pipeline_registry.get(pipeline_id)
    if not manifest:
        _fail_job(job_id, f"Unknown pipeline: {pipeline_id}")
        return

    # Check engine
    if engine_process.status not in ("ready", "busy"):
        _fail_job(job_id, "Engine not available")
        return

    if _is_cancelled(job_id):
        return

    image_bytes: Optional[bytes] = None
    image_filename = "input.png"
    try:
        image_bytes, image_filename, input_path = _load_input_file(params)
    except ValueError as e:
        _fail_job(job_id, str(e))
        return

    fps_meta = manifest.params.get("fps") or {}
    if fps_meta.get("from_input") and "fps" not in params and input_path:
        from app.media.ffmpeg import probe
        src_fps = (await probe(input_path)).get("fps")
        if src_fps:
            mult = params.get("multiplier", manifest.params.get("multiplier", {}).get("default", 1))
            params["fps"] = round(src_fps * (int(mult) if fps_meta.get("scale_by_multiplier") else 1))

    # Prepare loras
    loras_param = params.pop("_loras", [])

    # Free memory if model family will change
    family = manifest.family
    try:
        await _free_if_family_change(family)
    except Exception as e:
        logger.warning("Could not free memory: %s", e)

    # Patch workflow
    try:
        workflow = await patch_workflow(
            manifest, params, job_id,
            loras=loras_param,
            image_bytes=image_bytes,
            image_filename=image_filename,
        )
    except Exception as e:
        _fail_job(job_id, f"Workflow patch failed: {e}")
        return

    if _is_cancelled(job_id):
        return

    # Submit to ComfyUI
    _set_status(job_id, "running")
    broadcast("job_updated", {"id": job_id, "status": "running", "progress": 0})
    engine_process._set_status("busy")

    start_time = time.monotonic()
    last_max = 1

    async def on_progress(value: int, max_val: int) -> None:
        nonlocal last_max
        last_max = max_val or 1
        pct = int(value / last_max * 100)
        elapsed = time.monotonic() - start_time
        eta = (elapsed / max(value, 1)) * (last_max - value) if value else None
        broadcast("job_updated", {
            "id": job_id,
            "status": "running",
            "progress": pct,
            "eta_seconds": eta,
        })
        with get_session() as s:
            j = s.get(Job, job_id)
            if j:
                j.progress = pct
                j.eta_seconds = eta
                s.add(j)
                s.commit()

    def on_queued(prompt_id: str) -> None:
        with get_session() as s:
            j = s.get(Job, job_id)
            if j:
                j.engine_prompt_id = prompt_id
                s.add(j)
                s.commit()

    try:
        history = await comfy_client.run_workflow(
            workflow, progress_cb=on_progress, on_queued=on_queued
        )
    except ExecutionInterrupted:
        _mark_cancelled(job_id)
        engine_process._set_status("ready")
        return
    except RuntimeError as e:
        err = str(e)
        if _is_oom(err):
            logger.warning("OOM on job %s, trying fallback tier", job_id)
            success = await _oom_fallback(job_id, manifest, params, loras_param, image_bytes, image_filename)
            if success:
                return
        _fail_job(job_id, err)
        engine_process._set_status("ready")
        return
    except Exception as e:
        _fail_job(job_id, str(e))
        engine_process._set_status("ready")
        return

    if _is_cancelled(job_id):
        engine_process._set_status("ready")
        return

    # Post-process outputs
    _set_status(job_id, "postprocessing")
    try:
        assets = await save_job_outputs(job_id, pipeline_id, history, params)
        _finish_job(job_id, assets)
    except Exception as e:
        logger.error("Post-process error for job %s: %s", job_id, e)
        _fail_job(job_id, f"Post-processing failed: {e}")

    engine_process._set_status("ready")


async def _oom_fallback(
    job_id: str,
    manifest,
    params: dict,
    loras: list,
    image_bytes: Optional[bytes],
    image_filename: str,
) -> bool:
    """Retry with the manifest's fallback tier. Returns True if succeeded."""
    from app.pipelines.patcher import patch_workflow

    if not manifest.fallback:
        return False

    fallback_tier = manifest.fallback[0]
    if fallback_tier not in manifest.tiers or fallback_tier == params.get("_tier"):
        return False

    tier = manifest.tiers[fallback_tier]
    params = {**params, "_tier": fallback_tier}
    for key, tkey in (("width", "w"), ("height", "h"), ("frames", "frames")):
        if tkey in tier:
            params[key] = tier[tkey]

    await comfy_client.free_memory()

    try:
        workflow = await patch_workflow(
            manifest, params, job_id,
            loras=loras,
            image_bytes=image_bytes,
            image_filename=image_filename,
        )
        history = await comfy_client.run_workflow(workflow)
        assets = await save_job_outputs(job_id, manifest.id, history, params)
        _finish_job(job_id, assets, note=f"OOM fallback to {fallback_tier}")
        engine_process._set_status("ready")
        return True
    except ExecutionInterrupted:
        _mark_cancelled(job_id)
        engine_process._set_status("ready")
        return True
    except Exception as e:
        logger.error("OOM fallback also failed: %s", e)
        return False


_last_family: Optional[str] = None


async def _free_if_family_change(new_family: str) -> None:
    global _last_family
    if _last_family and _last_family != new_family:
        logger.info("Family change %s → %s, freeing VRAM", _last_family, new_family)
        await comfy_client.free_memory()
    _last_family = new_family


def _is_oom(err: str) -> bool:
    low = err.lower()
    return "out of memory" in low or "outofmemory" in low or "oom" in low.split()


def _load_input_file(params: dict) -> tuple[Optional[bytes], str, Optional[Path]]:
    """Pop _upload_id/_asset_path from params and read the file safely."""
    cfg = get_settings()
    upload_id = params.pop("_upload_id", None)
    asset_path = params.pop("_asset_path", None)

    if upload_id:
        base = (cfg.data_dir / "uploads").resolve()
        path = (base / str(upload_id)).resolve()
        if not path.is_relative_to(base) or not path.is_file():
            raise ValueError("Invalid upload reference")
        return path.read_bytes(), path.name, path

    if asset_path:
        base = cfg.outputs_dir.resolve()
        path = Path(str(asset_path)).resolve()
        if not path.is_relative_to(base) or not path.is_file():
            raise ValueError("Invalid asset reference")
        return path.read_bytes(), path.name, path

    return None, "input.png", None


def _is_cancelled(job_id: str) -> bool:
    with get_session() as s:
        job = s.get(Job, job_id)
        return bool(job and job.status == "cancelled")


def _mark_cancelled(job_id: str) -> None:
    with get_session() as s:
        job = s.get(Job, job_id)
        if job and job.status != "cancelled":
            job.status = "cancelled"
            job.finished_at = datetime.now(timezone.utc)
            s.add(job)
            s.commit()
    broadcast("job_updated", {"id": job_id, "status": "cancelled"})


def _set_status(job_id: str, status: str) -> None:
    with get_session() as s:
        job = s.get(Job, job_id)
        if job and job.status != "cancelled":
            job.status = status
            s.add(job)
            s.commit()


def _fail_job(job_id: str, error: str) -> None:
    with get_session() as s:
        job = s.get(Job, job_id)
        if job and job.status == "cancelled":
            return
        if job:
            job.status = "failed"
            job.error = error
            job.finished_at = datetime.now(timezone.utc)
            s.add(job)
            s.commit()
    broadcast("job_updated", {"id": job_id, "status": "failed", "error": error})
    logger.error("Job %s failed: %s", job_id, error)


def _finish_job(job_id: str, assets: list, note: str = "") -> None:
    with get_session() as s:
        job = s.get(Job, job_id)
        if job and job.status == "cancelled":
            return
        if job:
            job.status = "done"
            job.progress = 100
            job.finished_at = datetime.now(timezone.utc)
            if note:
                job.error = note  # repurpose as informational note
            s.add(job)
            s.commit()
    broadcast("job_updated", {
        "id": job_id,
        "status": "done",
        "progress": 100,
        "assets": [a.id for a in assets],
    })
    logger.info("Job %s done, %d assets", job_id, len(assets))
