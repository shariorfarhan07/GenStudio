"""
Output store — moves ComfyUI outputs into the GenStudio output tree,
generates thumbnails, embeds metadata, and creates Asset DB rows.
"""
from __future__ import annotations

import json
import logging
import struct
import zlib
from datetime import datetime, date
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.jobs.models import Asset
from app.media.ffmpeg import make_thumbnail, probe

logger = logging.getLogger(__name__)

VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".mov", ".avi"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def _today_dir() -> Path:
    cfg = get_settings()
    return cfg.outputs_dir / date.today().strftime("%Y-%m-%d")


def _engine_output_dir() -> Path:
    cfg = get_settings()
    return cfg.outputs_dir / "_engine"


async def save_job_outputs(
    job_id: str,
    pipeline_id: str,
    history: dict,
    params: dict,
) -> list[Asset]:
    """
    Scan ComfyUI history for output files, move them, create thumbnails,
    embed metadata, and return a list of Asset objects (not yet in DB).
    """
    from app.jobs.queue import get_session  # avoid circular at module level

    assets: list[Asset] = []
    out_dir = _today_dir() / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    outputs: dict = history.get("outputs", {})
    for node_id, node_out in outputs.items():
        for kind in ("images", "videos", "gifs"):
            for item in node_out.get(kind, []):
                filename: str = item.get("filename", "")
                subfolder: str = item.get("subfolder", "")
                if not filename:
                    continue

                # Locate the file in the engine output dir
                src_candidates = [
                    _engine_output_dir() / subfolder / filename,
                    _engine_output_dir() / filename,
                ]
                src: Path | None = None
                for c in src_candidates:
                    if c.exists():
                        src = c
                        break

                if not src:
                    logger.warning("Output file not found: %s/%s", subfolder, filename)
                    continue

                dest = out_dir / filename
                src.rename(dest)

                ext = dest.suffix.lower()
                asset_kind = "video" if ext in VIDEO_EXTS else "image"

                # Probe media
                media_info = await probe(dest) if asset_kind == "video" else _image_size(dest)

                # Thumbnail
                thumb_dir = out_dir / "thumbs"
                thumb_path = thumb_dir / (dest.stem + ".jpg")
                await make_thumbnail(dest, thumb_path)

                # Embed metadata
                prompt_text = params.get("prompt", "")
                seed = params.get("seed")
                if asset_kind == "image":
                    _embed_png_metadata(dest, params)

                asset = Asset(
                    job_id=job_id,
                    kind=asset_kind,
                    path=str(dest),
                    thumb_path=str(thumb_path) if thumb_path.exists() else "",
                    width=media_info.get("width"),
                    height=media_info.get("height"),
                    frames=media_info.get("frames"),
                    fps=media_info.get("fps"),
                    duration=media_info.get("duration"),
                    seed=seed,
                    pipeline_id=pipeline_id,
                    prompt=prompt_text[:500] if prompt_text else None,
                )

                with get_session() as s:
                    s.add(asset)
                    s.commit()
                    s.refresh(asset)

                assets.append(asset)

    return assets


def _image_size(path: Path) -> dict:
    try:
        from PIL import Image
        with Image.open(path) as im:
            return {"width": im.width, "height": im.height}
    except Exception:
        return {}


def _embed_png_metadata(path: Path, params: dict) -> None:
    """Embed generation params as a tEXt chunk in a PNG file."""
    try:
        data = path.read_bytes()
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            return
        public = {k: v for k, v in params.items() if not k.startswith("_")}
        meta_str = json.dumps(public, ensure_ascii=False)
        keyword = b"GenStudio"
        text_chunk = keyword + b"\x00" + meta_str.encode("latin-1", errors="replace")
        crc = zlib.crc32(b"tEXt" + text_chunk) & 0xFFFFFFFF
        chunk = struct.pack(">I", len(text_chunk)) + b"tEXt" + text_chunk + struct.pack(">I", crc)
        # Insert after IHDR chunk (bytes 8-33 in a well-formed PNG)
        new_data = data[:33] + chunk + data[33:]
        path.write_bytes(new_data)
    except Exception as e:
        logger.debug("Could not embed PNG metadata: %s", e)
