from fastapi import APIRouter
from app.engine.process import engine_process
from app.gpu.monitor import get_gpu_stats, get_system_stats
from app.config import get_settings
import platform, sys

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("")
async def system_info():
    cfg = get_settings()
    gpu = get_gpu_stats()
    sys_stats = get_system_stats()
    return {
        "engine_status": engine_process.status,
        "gpu": gpu,
        "system": sys_stats,
        "python_version": sys.version,
        "platform": platform.platform(),
        "vram_warn_threshold_mb": int(cfg.vram_warn_threshold * 1024),
    }


@router.post("/engine/restart")
async def restart_engine():
    import asyncio
    asyncio.create_task(engine_process.restart())
    return {"ok": True}


@router.get("/engine/log")
async def engine_log():
    return {"lines": engine_process.log_tail}
