"""
SQLModel database models for GenStudio.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def new_id() -> str:
    return str(uuid.uuid4())


class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    id: str = Field(default_factory=new_id, primary_key=True)
    batch_id: Optional[str] = Field(default=None, index=True)
    parent_job_id: Optional[str] = Field(default=None)
    pipeline_id: str = Field(index=True)
    task: str = Field(default="")
    params_json: str = Field(default="{}")
    status: str = Field(default="queued", index=True)  # queued|preparing|running|postprocessing|done|failed|cancelled
    progress: int = Field(default=0)   # 0-100
    eta_seconds: Optional[float] = Field(default=None)
    error: Optional[str] = Field(default=None)
    engine_prompt_id: Optional[str] = Field(default=None)
    attempts: int = Field(default=0)
    priority: int = Field(default=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = Field(default=None)
    finished_at: Optional[datetime] = Field(default=None)


class Asset(SQLModel, table=True):
    __tablename__ = "assets"

    id: str = Field(default_factory=new_id, primary_key=True)
    job_id: Optional[str] = Field(default=None, index=True)
    kind: str = Field(default="image")  # image|video
    path: str = Field(default="")
    thumb_path: str = Field(default="")
    width: Optional[int] = Field(default=None)
    height: Optional[int] = Field(default=None)
    frames: Optional[int] = Field(default=None)
    fps: Optional[float] = Field(default=None)
    duration: Optional[float] = Field(default=None)
    seed: Optional[int] = Field(default=None)
    pipeline_id: Optional[str] = Field(default=None, index=True)
    prompt: Optional[str] = Field(default=None)
    favorite: bool = Field(default=False)
    tags: str = Field(default="")  # JSON array
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Preset(SQLModel, table=True):
    __tablename__ = "presets"

    id: str = Field(default_factory=new_id, primary_key=True)
    name: str = Field(unique=True)
    pipeline_id: str = Field(index=True)
    params_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class InstalledModel(SQLModel, table=True):
    __tablename__ = "installed_models"

    catalog_id: str = Field(primary_key=True)
    path: str = Field(default="")
    size_bytes: int = Field(default=0)
    sha256: Optional[str] = Field(default=None)
    installed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_used: Optional[datetime] = Field(default=None)


class Lora(SQLModel, table=True):
    __tablename__ = "loras"

    id: str = Field(default_factory=new_id, primary_key=True)
    file: str = Field(unique=True)              # filename relative to models/loras/
    display_name: str = Field(default="")
    base_family: str = Field(default="")        # wan22 | flux2 | zimage | ltx2
    trigger_words: str = Field(default="")      # comma-separated
    default_weight: float = Field(default=1.0)
    preview_path: Optional[str] = Field(default=None)
    added_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
