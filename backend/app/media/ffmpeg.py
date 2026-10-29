"""
ffmpeg/ffprobe helpers.
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def _ffprobe_bin() -> str:
    return shutil.which("ffprobe") or "ffprobe"


def _ffmpeg_bin() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


async def probe(path: Path) -> dict:
    """Return a dict with width, height, fps, duration, frames for a media file."""
    cmd = [
        _ffprobe_bin(),
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        str(path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, _ = await proc.communicate()
    try:
        data = json.loads(out)
    except Exception:
        return {}

    result: dict = {}
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            result["width"] = stream.get("width")
            result["height"] = stream.get("height")
            # fps as float
            fps_str = stream.get("r_frame_rate", "0/1")
            try:
                num, den = fps_str.split("/")
                result["fps"] = round(int(num) / int(den), 3) if int(den) else 0
            except Exception:
                result["fps"] = 0
            nb_frames = stream.get("nb_frames")
            if nb_frames:
                result["frames"] = int(nb_frames)
            break

    fmt = data.get("format", {})
    dur = fmt.get("duration")
    if dur:
        result["duration"] = float(dur)

    return result


async def make_thumbnail(src: Path, dest: Path, size: int = 320) -> bool:
    """Extract a thumbnail from an image or video. Returns True on success."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() in (".mp4", ".webm", ".mkv", ".mov", ".avi"):
        cmd = [
            _ffmpeg_bin(), "-y",
            "-ss", "0",
            "-i", str(src),
            "-vframes", "1",
            "-vf", f"scale={size}:-1",
            str(dest),
        ]
    else:
        cmd = [
            _ffmpeg_bin(), "-y",
            "-i", str(src),
            "-vf", f"scale={size}:-1",
            str(dest),
        ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    rc = await proc.wait()
    return rc == 0


async def remux_to_mp4(src: Path, dest: Path) -> bool:
    """Remux a video file to MP4 without re-encoding."""
    cmd = [
        _ffmpeg_bin(), "-y",
        "-i", str(src),
        "-c", "copy",
        str(dest),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    rc = await proc.wait()
    return rc == 0
