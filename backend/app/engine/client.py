"""
Async client for the ComfyUI REST and WebSocket API.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Callable

import httpx
import websockets

from app.config import get_settings

logger = logging.getLogger(__name__)


def _base_url() -> str:
    cfg = get_settings()
    return f"http://{cfg.engine_host}:{cfg.engine_port}"


def _ws_url() -> str:
    cfg = get_settings()
    return f"ws://{cfg.engine_host}:{cfg.engine_port}/ws"


class ExecutionInterrupted(RuntimeError):
    """Raised when ComfyUI reports that the prompt was interrupted."""


class ComfyClient:
    """Thin async wrapper around the ComfyUI HTTP + WS API."""

    def __init__(self) -> None:
        self._client_id = str(uuid.uuid4())

    # ── REST helpers ──────────────────────────────────────────────────────

    async def system_stats(self) -> dict:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{_base_url()}/system_stats")
            r.raise_for_status()
            return r.json()

    async def object_info(self) -> dict:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.get(f"{_base_url()}/object_info")
            r.raise_for_status()
            return r.json()

    async def queue_prompt(self, workflow: dict[str, Any]) -> str:
        """Submit a workflow and return the prompt_id."""
        payload = {"prompt": workflow, "client_id": self._client_id}
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post(f"{_base_url()}/prompt", json=payload)
            r.raise_for_status()
            return r.json()["prompt_id"]

    async def get_history(self, prompt_id: str) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{_base_url()}/history/{prompt_id}")
            r.raise_for_status()
            return r.json()

    async def get_file(self, filename: str, subfolder: str = "", ftype: str = "output") -> bytes:
        params: dict[str, str] = {"filename": filename, "type": ftype}
        if subfolder:
            params["subfolder"] = subfolder
        async with httpx.AsyncClient(timeout=120.0) as c:
            r = await c.get(f"{_base_url()}/view", params=params)
            r.raise_for_status()
            return r.content

    async def upload_image(self, data: bytes, filename: str, overwrite: bool = True) -> str:
        """Upload an image to ComfyUI's input folder, return the stored filename."""
        files = {"image": (filename, data, "image/png")}
        data_form = {"overwrite": "true" if overwrite else "false", "type": "input"}
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post(f"{_base_url()}/upload/image", files=files, data=data_form)
            r.raise_for_status()
            return r.json()["name"]

    async def interrupt(self) -> None:
        async with httpx.AsyncClient(timeout=5.0) as c:
            await c.post(f"{_base_url()}/interrupt")

    async def free_memory(self, unload_models: bool = True) -> None:
        payload = {"unload_models": unload_models, "free_memory": True}
        async with httpx.AsyncClient(timeout=10.0) as c:
            try:
                await c.post(f"{_base_url()}/free", json=payload)
            except Exception as e:
                logger.debug("free_memory error (ignored): %s", e)

    # ── Execution ─────────────────────────────────────────────────────────

    async def run_workflow(
        self,
        workflow: dict[str, Any],
        progress_cb: Callable[[int, int], Any] | None = None,
        on_queued: Callable[[str], Any] | None = None,
        timeout: float = 7200.0,
        poll_interval: float = 5.0,
    ) -> dict:
        """
        Connect the event socket, submit the workflow, and wait for it to
        finish. Returns the history entry for the prompt. Raises
        ExecutionInterrupted if cancelled and RuntimeError on failure.
        """
        url = f"{_ws_url()}?clientId={self._client_id}"
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        async with websockets.connect(url, max_size=20 * 1024 * 1024) as ws:
            prompt_id = await self.queue_prompt(workflow)
            if on_queued:
                res = on_queued(prompt_id)
                if asyncio.iscoroutine(res):
                    await res

            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise RuntimeError(f"Timed out waiting for prompt {prompt_id}")
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=min(poll_interval, remaining))
                except asyncio.TimeoutError:
                    entry = await self._poll_history(prompt_id)
                    if entry is not None:
                        return entry
                    continue

                if isinstance(raw, bytes):
                    continue
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                mtype = msg.get("type", "")
                data = msg.get("data", {}) or {}
                if data.get("prompt_id") not in (None, prompt_id):
                    continue

                if mtype == "progress":
                    if progress_cb:
                        res = progress_cb(data.get("value", 0), data.get("max", 1))
                        if asyncio.iscoroutine(res):
                            await res
                elif mtype == "execution_interrupted":
                    raise ExecutionInterrupted("Execution interrupted")
                elif mtype == "execution_error":
                    raise RuntimeError(data.get("exception_message") or "unknown error")
                elif mtype == "execution_success":
                    break
                elif mtype == "executing" and data.get("node") is None and data.get("prompt_id") == prompt_id:
                    break

        for _ in range(10):
            entry = await self._poll_history(prompt_id)
            if entry is not None:
                return entry
            await asyncio.sleep(0.5)
        return {}

    async def _poll_history(self, prompt_id: str) -> dict | None:
        """Return the finished history entry, or None if still running."""
        try:
            hist = await self.get_history(prompt_id)
        except Exception as e:
            logger.debug("history poll failed: %s", e)
            return None
        entry = hist.get(prompt_id)
        if not entry:
            return None
        status = entry.get("status", {}) or {}
        if status.get("status_str") == "error":
            msg = "execution error"
            for m in status.get("messages", []):
                if m and m[0] == "execution_error":
                    msg = (m[1] or {}).get("exception_message", msg)
                if m and m[0] == "execution_interrupted":
                    raise ExecutionInterrupted("Execution interrupted")
            raise RuntimeError(msg)
        if status.get("completed") or entry.get("outputs"):
            return entry
        return None


# module-level singleton
comfy_client = ComfyClient()
