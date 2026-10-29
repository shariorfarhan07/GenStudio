import secrets

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.config import Settings, get_settings, save_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
async def get():
    cfg = get_settings()
    d = cfg.model_dump(mode="json")
    # Mask token
    if d.get("hf_token"):
        d["hf_token"] = "***"
    if d.get("lan_token"):
        d["lan_token"] = d["lan_token"][:8] + "…"
    return d


@router.put("")
async def update(body: dict):
    cfg = get_settings()
    existing = cfg.model_dump()
    # Merge, but preserve sensitive fields if masked
    for k, v in body.items():
        if k in ("hf_token", "lan_token") and (str(v).startswith("*") or str(v).endswith("…")):
            continue
        if hasattr(cfg, k):
            existing[k] = v
    try:
        new_cfg = Settings(**existing)
    except ValidationError as e:
        raise HTTPException(422, str(e))
    save_settings(new_cfg)
    return {"ok": True}


@router.post("/generate-lan-token")
async def generate_lan_token():
    token = secrets.token_urlsafe(24)
    cfg = get_settings()
    d = cfg.model_dump()
    d["lan_token"] = token
    save_settings(Settings(**d))
    return {"token": token}
