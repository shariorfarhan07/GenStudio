from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from app.config import get_settings
from app.jobs.models import Lora
from app.jobs.queue import get_session

router = APIRouter(prefix="/api/loras", tags=["loras"])


class UpdateLora(BaseModel):
    display_name: Optional[str] = None
    base_family: Optional[str] = None
    trigger_words: Optional[str] = None
    default_weight: Optional[float] = None


@router.get("")
async def list_loras(family: Optional[str] = None):
    with get_session() as s:
        stmt = select(Lora)
        if family:
            stmt = stmt.where(Lora.base_family == family)
        loras = s.exec(stmt).all()
        return [_lora_dict(l) for l in loras]


@router.post("/rescan")
async def rescan_loras():
    """Scan models/loras/ and add any new .safetensors files to the DB."""
    cfg = get_settings()
    lora_dir = cfg.models_dir / "loras"
    lora_dir.mkdir(parents=True, exist_ok=True)

    added = 0
    with get_session() as s:
        existing = {l.file for l in s.exec(select(Lora)).all()}
        for f in lora_dir.glob("*.safetensors"):
            rel = f.name
            if rel not in existing:
                lora = Lora(
                    file=rel,
                    display_name=f.stem.replace("_", " ").replace("-", " ").title(),
                )
                s.add(lora)
                added += 1
        s.commit()
    return {"added": added}


@router.patch("/{lora_id}")
async def update_lora(lora_id: str, req: UpdateLora):
    with get_session() as s:
        lora = s.get(Lora, lora_id)
        if not lora:
            raise HTTPException(404, "LoRA not found")
        if req.display_name is not None:
            lora.display_name = req.display_name
        if req.base_family is not None:
            lora.base_family = req.base_family
        if req.trigger_words is not None:
            lora.trigger_words = req.trigger_words
        if req.default_weight is not None:
            lora.default_weight = req.default_weight
        s.add(lora)
        s.commit()
        s.refresh(lora)
        return _lora_dict(lora)


def _lora_dict(l: Lora) -> dict:
    return {
        "id": l.id,
        "file": l.file,
        "display_name": l.display_name,
        "base_family": l.base_family,
        "trigger_words": l.trigger_words,
        "default_weight": l.default_weight,
        "preview_path": l.preview_path,
    }
