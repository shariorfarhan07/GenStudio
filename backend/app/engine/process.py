"""
Manages the ComfyUI subprocess: spawn, health-poll, restart, log capture.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 2.0   # seconds between health checks while starting
_READY_TIMEOUT = 120   # seconds to wait for ComfyUI to respond
_RESTART_BACKOFF = [5, 10, 20, 30]  # seconds between restart attempts


class EngineProcess:
    """Singleton that owns the ComfyUI subprocess."""

    def __init__(self) -> None:
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._log_task: Optional[asyncio.Task] = None
        self._status: str = "stopped"   # stopped | starting | ready | busy | crashed
        self._restart_attempt: int = 0
        self._log_tail: list[str] = []   # last 200 lines
        self._status_callbacks: list = []

    @property
    def status(self) -> str:
        return self._status

    @property
    def log_tail(self) -> list[str]:
        return self._log_tail[-200:]

    def add_status_callback(self, cb) -> None:
        self._status_callbacks.append(cb)

    def _set_status(self, s: str) -> None:
        self._status = s
        for cb in self._status_callbacks:
            try:
                cb(s)
            except Exception:
                pass

    def _engine_url(self) -> str:
        cfg = get_settings()
        return f"http://{cfg.engine_host}:{cfg.engine_port}"

    def _build_cmd(self) -> list[str]:
        cfg = get_settings()
        comfyui = cfg.engine_dir / "ComfyUI" / "main.py"
        python = cfg.engine_dir / "venv" / "Scripts" / "python.exe"
        if not python.exists():
            python = cfg.engine_dir / "venv" / "bin" / "python"

        extra_yaml = cfg.engine_dir / "extra_model_paths.yaml"
        outputs_engine = cfg.outputs_dir / "_engine"
        outputs_engine.mkdir(parents=True, exist_ok=True)
        uploads = cfg.data_dir / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(python), str(comfyui),
            "--listen", cfg.engine_host,
            "--port", str(cfg.engine_port),
            "--disable-auto-launch",
            "--output-directory", str(outputs_engine),
            "--input-directory", str(uploads),
            "--preview-method", cfg.engine_preview_method,
        ]
        if extra_yaml.exists():
            cmd += ["--extra-model-paths-config", str(extra_yaml)]
        if cfg.engine_reserve_vram:
            cmd += ["--reserve-vram", str(cfg.engine_reserve_vram)]
        if cfg.engine_use_sage_attention:
            cmd.append("--use-sage-attention")
        return cmd

    async def start(self) -> None:
        if self._proc and self._proc.returncode is None:
            logger.info("Engine already running (pid=%s)", self._proc.pid)
            return

        cfg = get_settings()
        comfyui_main = cfg.engine_dir / "ComfyUI" / "main.py"
        if not comfyui_main.exists():
            logger.warning("ComfyUI not installed at %s — engine won't start", comfyui_main)
            self._set_status("stopped")
            return

        cmd = self._build_cmd()
        logger.info("Starting ComfyUI: %s", " ".join(cmd))
        self._set_status("starting")

        log_path = cfg.logs_dir / "engine.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = open(log_path, "a", encoding="utf-8")

        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(cfg.engine_dir / "ComfyUI"),
        )
        self._log_task = asyncio.create_task(
            self._stream_logs(log_file), name="engine-logs"
        )

        # Wait until /system_stats responds
        deadline = time.monotonic() + _READY_TIMEOUT
        async with httpx.AsyncClient(timeout=4.0) as client:
            while time.monotonic() < deadline:
                if self._proc.returncode is not None:
                    logger.error("ComfyUI exited early (rc=%s)", self._proc.returncode)
                    self._set_status("crashed")
                    return
                try:
                    r = await client.get(f"{self._engine_url()}/system_stats")
                    if r.status_code == 200:
                        logger.info("ComfyUI ready (pid=%s)", self._proc.pid)
                        self._set_status("ready")
                        self._restart_attempt = 0
                        return
                except Exception:
                    pass
                await asyncio.sleep(_POLL_INTERVAL)

        logger.error("ComfyUI did not become ready within %ss", _READY_TIMEOUT)
        self._set_status("crashed")

    async def stop(self) -> None:
        if self._proc and self._proc.returncode is None:
            logger.info("Stopping ComfyUI (pid=%s)", self._proc.pid)
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=10)
            except asyncio.TimeoutError:
                self._proc.kill()
        self._set_status("stopped")

    async def restart(self) -> None:
        logger.info("Restarting ComfyUI (attempt %s)", self._restart_attempt)
        await self.stop()
        backoff = _RESTART_BACKOFF[min(self._restart_attempt, len(_RESTART_BACKOFF) - 1)]
        self._restart_attempt += 1
        logger.info("Waiting %ss before restart", backoff)
        await asyncio.sleep(backoff)
        await self.start()

    async def _stream_logs(self, log_file) -> None:
        assert self._proc and self._proc.stdout
        try:
            async for raw in self._proc.stdout:
                line = raw.decode("utf-8", errors="replace").rstrip()
                self._log_tail.append(line)
                if len(self._log_tail) > 500:
                    self._log_tail = self._log_tail[-400:]
                log_file.write(line + "\n")
                log_file.flush()
        except Exception as e:
            logger.debug("Log stream ended: %s", e)
        finally:
            log_file.close()
            if self._proc.returncode is not None and self._status not in ("stopped",):
                logger.warning("ComfyUI process ended unexpectedly (rc=%s)", self._proc.returncode)
                self._set_status("crashed")


# module-level singleton
engine_process = EngineProcess()
