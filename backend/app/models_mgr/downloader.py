"""
Resumable HuggingFace model downloader with progress events.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

import httpx

from app.config import get_settings
from app.jobs.events import broadcast

logger = logging.getLogger(__name__)

# Active downloads: catalog_id -> asyncio.Task
_active: dict[str, asyncio.Task] = {}


def is_downloading(catalog_id: str) -> bool:
    t = _active.get(catalog_id)
    return t is not None and not t.done()


def cancel_download(catalog_id: str) -> None:
    t = _active.get(catalog_id)
    if t:
        t.cancel()


async def download_model(catalog_id: str, entry: dict) -> None:
    """Start an async download for catalog entry. No-op if already running."""
    if is_downloading(catalog_id):
        return
    task = asyncio.create_task(
        _download(catalog_id, entry), name=f"dl-{catalog_id}"
    )
    _active[catalog_id] = task


async def _download(catalog_id: str, entry: dict) -> None:
    cfg = get_settings()
    dest_folder = cfg.models_dir / entry.get("folder", "diffusion_models")
    dest_folder.mkdir(parents=True, exist_ok=True)
    filename = entry["filename"]
    dest = dest_folder / filename
    tmp = dest.with_suffix(dest.suffix + ".part")

    # Check disk space
    needed = entry.get("size_bytes", 0)
    free = shutil.disk_usage(cfg.models_dir).free
    if needed and free < needed * 1.05:
        broadcast("download_error", {
            "catalog_id": catalog_id,
            "error": f"Not enough disk space (need {needed//1024//1024} MB, have {free//1024//1024} MB)",
        })
        return

    # Build URL (prefer direct url, else huggingface)
    url = entry.get("url")
    if not url:
        repo = entry.get("repo", "")
        path = entry.get("path", filename)
        url = f"https://huggingface.co/{repo}/resolve/main/{path}"

    headers: dict[str, str] = {}
    if cfg.hf_token:
        headers["Authorization"] = f"Bearer {cfg.hf_token}"

    # Resume support
    resume_pos = tmp.stat().st_size if tmp.exists() else 0
    if resume_pos:
        headers["Range"] = f"bytes={resume_pos}-"
        logger.info("Resuming %s from byte %d", filename, resume_pos)

    broadcast("download_started", {"catalog_id": catalog_id, "filename": filename})

    try:
        async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
            async with client.stream("GET", url, headers=headers) as resp:
                if resp.status_code == 416:  # Range not satisfiable — file complete
                    tmp.rename(dest)
                    _finish(catalog_id, dest, entry)
                    return
                resp.raise_for_status()
                total = int(resp.headers.get("Content-Length", 0)) + resume_pos
                downloaded = resume_pos

                mode = "ab" if resume_pos else "wb"
                with open(tmp, mode) as f:
                    async for chunk in resp.aiter_bytes(chunk_size=1024 * 1024):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = int(downloaded / total * 100)
                            broadcast("download_progress", {
                                "catalog_id": catalog_id,
                                "filename": filename,
                                "downloaded": downloaded,
                                "total": total,
                                "percent": pct,
                            })

        # Verify sha256 if provided
        expected_sha = entry.get("sha256")
        if expected_sha:
            actual = _sha256(tmp)
            if actual != expected_sha.lower():
                tmp.unlink(missing_ok=True)
                broadcast("download_error", {
                    "catalog_id": catalog_id,
                    "error": f"SHA256 mismatch (expected {expected_sha}, got {actual})",
                })
                return

        tmp.rename(dest)
        _finish(catalog_id, dest, entry)

    except asyncio.CancelledError:
        broadcast("download_cancelled", {"catalog_id": catalog_id})
        logger.info("Download cancelled: %s", catalog_id)
    except Exception as e:
        broadcast("download_error", {"catalog_id": catalog_id, "error": str(e)})
        logger.error("Download failed %s: %s", catalog_id, e)
    finally:
        _active.pop(catalog_id, None)


def _finish(catalog_id: str, path: Path, entry: dict) -> None:
    broadcast("download_done", {
        "catalog_id": catalog_id,
        "filename": entry["filename"],
        "path": str(path),
    })
    logger.info("Downloaded: %s → %s", catalog_id, path)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
