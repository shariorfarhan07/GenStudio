import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, col, select

from app.jobs.models import Asset
from app.jobs.queue import get_session

router = APIRouter(prefix="/api/assets", tags=["assets"])


class UpdateAsset(BaseModel):
    favorite: Optional[bool] = None
    tags: Optional[list[str]] = None


class PostprocessRequest(BaseModel):
    op: str   # upscale_image | upscale_video | interpolate
    options: dict = {}


@router.get("")
async def list_assets(
    kind: Optional[str] = None,
    pipeline_id: Optional[str] = None,
    fav: Optional[bool] = None,
    q: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
):
    with get_session() as s:
        stmt = select(Asset).order_by(col(Asset.created_at).desc())
        if kind:
            stmt = stmt.where(Asset.kind == kind)
        if pipeline_id:
            stmt = stmt.where(Asset.pipeline_id == pipeline_id)
        if fav is not None:
            stmt = stmt.where(Asset.favorite == fav)
        if q:
            stmt = stmt.where(col(Asset.prompt).contains(q))
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        assets = s.exec(stmt).all()
        return [_asset_dict(a) for a in assets]


@router.get("/{asset_id}")
async def get_asset(asset_id: str):
    with get_session() as s:
        a = s.get(Asset, asset_id)
        if not a:
            raise HTTPException(404, "Asset not found")
        return _asset_dict(a)


@router.patch("/{asset_id}")
async def update_asset(asset_id: str, req: UpdateAsset):
    with get_session() as s:
        a = s.get(Asset, asset_id)
        if not a:
            raise HTTPException(404, "Asset not found")
        if req.favorite is not None:
            a.favorite = req.favorite
        if req.tags is not None:
            a.tags = json.dumps(req.tags)
        s.add(a)
        s.commit()
        s.refresh(a)
        return _asset_dict(a)


@router.delete("/{asset_id}")
async def delete_asset(asset_id: str):
    with get_session() as s:
        a = s.get(Asset, asset_id)
        if not a:
            raise HTTPException(404, "Asset not found")
        # Delete files
        for p in (a.path, a.thumb_path):
            if p:
                try:
                    Path(p).unlink(missing_ok=True)
                except Exception:
                    pass
        s.delete(a)
        s.commit()
    return {"ok": True}


@router.post("/{asset_id}/postprocess")
async def postprocess(asset_id: str, req: PostprocessRequest):
    from app.jobs.models import Job
    from app.jobs.queue import enqueue
    from app.pipelines.registry import pipeline_registry
    import json as _json

    with get_session() as s:
        a = s.get(Asset, asset_id)
        if not a:
            raise HTTPException(404, "Asset not found")

    op = req.op
    pipeline_map = {
        "upscale_image": "upscale_image_esrgan",
        "upscale_video": "upscale_video_esrgan",
        "interpolate": "interpolate_rife",
    }
    pipeline_id = pipeline_map.get(op)
    if not pipeline_id:
        raise HTTPException(400, f"Unknown op: {op}")

    manifest = pipeline_registry.get(pipeline_id)
    if not manifest:
        raise HTTPException(422, f"Pipeline not installed: {pipeline_id}")

    params = {**req.options, "_asset_path": a.path}
    job = Job(
        pipeline_id=pipeline_id,
        task=manifest.task,
        params_json=_json.dumps(params),
        parent_job_id=a.job_id,
    )
    enqueue(job)
    return {"job_id": job.id}


def _asset_dict(a: Asset) -> dict:
    return {
        "id": a.id,
        "job_id": a.job_id,
        "kind": a.kind,
        "path": a.path,
        "thumb_path": a.thumb_path,
        "width": a.width,
        "height": a.height,
        "frames": a.frames,
        "fps": a.fps,
        "duration": a.duration,
        "seed": a.seed,
        "pipeline_id": a.pipeline_id,
        "prompt": a.prompt,
        "favorite": a.favorite,
        "tags": json.loads(a.tags) if a.tags else [],
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
