import shutil
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.models_mgr.downloader import cancel_download, download_model, is_downloading

router = APIRouter(prefix="/api/models", tags=["models"])

_CATALOG_PATH = Path(__file__).parents[1] / "models_mgr" / "catalog.yaml"


def _load_catalog() -> dict:
    if not _CATALOG_PATH.exists():
        return {}
    return yaml.safe_load(_CATALOG_PATH.read_text("utf-8")) or {}


def _check_installed(entry: dict, cfg) -> bool:
    folder = cfg.models_dir / entry.get("folder", "diffusion_models")
    filename = entry.get("filename", "")
    return (folder / filename).exists()


@router.get("")
async def list_models():
    cfg = get_settings()
    catalog = _load_catalog()
    result = []
    for cat_id, entry in catalog.items():
        installed = _check_installed(entry, cfg)
        result.append({
            "id": cat_id,
            "filename": entry.get("filename"),
            "label": entry.get("label", entry.get("filename")),
            "description": entry.get("description", ""),
            "pack": entry.get("pack", ""),
            "folder": entry.get("folder", ""),
            "size_gb": round(entry.get("size_bytes", 0) / 1024**3, 2),
            "license": entry.get("license", ""),
            "requires_token": entry.get("requires_token", False),
            "installed": installed,
            "downloading": is_downloading(cat_id),
        })
    return result


@router.post("/{cat_id}/install")
async def install_model(cat_id: str):
    catalog = _load_catalog()
    entry = catalog.get(cat_id)
    if not entry:
        raise HTTPException(404, f"Model not in catalog: {cat_id}")
    await download_model(cat_id, entry)
    return {"ok": True, "message": "Download started"}


@router.delete("/{cat_id}")
async def remove_model(cat_id: str):
    cfg = get_settings()
    catalog = _load_catalog()
    entry = catalog.get(cat_id)
    if not entry:
        raise HTTPException(404, f"Model not in catalog: {cat_id}")
    path = cfg.models_dir / entry.get("folder", "diffusion_models") / entry["filename"]
    if path.exists():
        path.unlink()
    return {"ok": True}


@router.post("/{cat_id}/cancel")
async def cancel_install(cat_id: str):
    cancel_download(cat_id)
    return {"ok": True}


@router.get("/disk")
async def disk_usage():
    cfg = get_settings()
    usage = shutil.disk_usage(cfg.models_dir)
    return {
        "models_dir": str(cfg.models_dir),
        "total_gb": round(usage.total / 1024**3, 1),
        "used_gb": round(usage.used / 1024**3, 1),
        "free_gb": round(usage.free / 1024**3, 1),
    }
