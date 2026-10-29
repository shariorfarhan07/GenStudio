"""
GenStudio configuration — all paths and tunables live here.
Settings are persisted to data/settings.json; env-vars override at startup.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

# ── Resolved root (I:\AI) ──────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]          # I:\AI\backend\app → I:\AI


class Settings(BaseModel):
    # Paths
    root: Path = ROOT
    models_dir: Path = ROOT / "models"
    outputs_dir: Path = ROOT / "outputs"
    data_dir: Path = ROOT / "data"
    logs_dir: Path = ROOT / "logs"
    engine_dir: Path = ROOT / "engine"
    frontend_dist: Path = ROOT / "frontend" / "dist"

    # Backend server
    host: str = "127.0.0.1"
    port: int = 8700
    lan_access: bool = False
    lan_token: str = ""

    # ComfyUI engine
    engine_host: str = "127.0.0.1"
    engine_port: int = 8188
    engine_reserve_vram: float = 0.6      # GB to reserve for OS / overhead
    engine_preview_method: str = "auto"   # auto | latent2rgb | taesd | none
    engine_use_sage_attention: bool = False

    # Generation defaults
    default_steps: int = 20
    default_cfg: float = 7.0
    default_seed: int = -1               # -1 = random

    # HuggingFace
    hf_token: str = ""

    # GPU budget warning threshold (GB)
    vram_warn_threshold: float = 11.5

    # Attention backend (sdpa | xformers | sage)
    attention_backend: Literal["sdpa", "xformers", "sage"] = "sdpa"


_SETTINGS_FILE: Path | None = None
_settings: Settings | None = None


def _settings_path() -> Path:
    global _SETTINGS_FILE
    if _SETTINGS_FILE is None:
        _SETTINGS_FILE = ROOT / "data" / "settings.json"
    return _SETTINGS_FILE


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        p = _settings_path()
        if p.exists():
            try:
                data = json.loads(p.read_text("utf-8"))
                _settings = Settings(**data)
            except Exception:
                _settings = Settings()
        else:
            _settings = Settings()
        # env overrides
        if hf := os.environ.get("HF_TOKEN"):
            _settings.hf_token = hf
        if token := os.environ.get("GENSTUDIO_LAN_TOKEN"):
            _settings.lan_token = token
    return _settings


def save_settings(s: Settings) -> None:
    global _settings
    _settings = s
    p = _settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        s.model_dump_json(indent=2, mode="json"),
        encoding="utf-8",
    )
