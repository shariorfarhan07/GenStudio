"""
GPU + RAM monitor — broadcasts stats every 2 seconds via the event bus.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import psutil

logger = logging.getLogger(__name__)

try:
    import pynvml
    pynvml.nvmlInit()
    _nvml_ok = True
except Exception:
    _nvml_ok = False
    logger.warning("pynvml not available — GPU stats will be zeros")


def get_gpu_stats() -> dict:
    stats = {
        "name": "Unknown GPU",
        "vram_total_mb": 0,
        "vram_used_mb": 0,
        "vram_free_mb": 0,
        "utilization": 0,
        "temperature": 0,
    }
    if not _nvml_ok:
        return stats
    try:
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        name = pynvml.nvmlDeviceGetName(handle)
        stats.update({
            "name": name if isinstance(name, str) else name.decode("utf-8"),
            "vram_total_mb": info.total // 1024 // 1024,
            "vram_used_mb": info.used // 1024 // 1024,
            "vram_free_mb": info.free // 1024 // 1024,
            "utilization": util.gpu,
            "temperature": temp,
        })
    except Exception as e:
        logger.debug("NVML read error: %s", e)
    return stats


def get_system_stats() -> dict:
    vm = psutil.virtual_memory()
    return {
        "ram_total_mb": vm.total // 1024 // 1024,
        "ram_used_mb": vm.used // 1024 // 1024,
        "ram_free_mb": vm.available // 1024 // 1024,
        "ram_percent": vm.percent,
    }


_monitor_task: Optional[asyncio.Task] = None


async def start_monitor() -> None:
    global _monitor_task
    _monitor_task = asyncio.create_task(_loop(), name="gpu-monitor")


async def stop_monitor() -> None:
    if _monitor_task:
        _monitor_task.cancel()


async def _loop() -> None:
    from app.jobs.events import broadcast
    from app.engine.process import engine_process

    while True:
        try:
            gpu = get_gpu_stats()
            sys = get_system_stats()
            broadcast("stats", {
                "gpu": gpu,
                "system": sys,
                "engine_status": engine_process.status,
            })
        except Exception as e:
            logger.debug("Monitor loop error: %s", e)
        await asyncio.sleep(2.0)
