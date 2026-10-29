"""
Pipeline registry — loads all template+manifest pairs from disk, validates
node classes against ComfyUI's /object_info, and exposes the list to the API.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from app.config import get_settings

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"

_MODEL_INPUT_KEYS = (
    "unet_name", "clip_name", "clip_name1", "clip_name2",
    "vae_name", "model_name", "ckpt_name", "lora_name",
)


class PipelineManifest:
    """Parsed manifest.yaml for one pipeline."""

    def __init__(self, data: dict, template_dir: Path) -> None:
        self.id: str = data["id"]
        self.task: str = data["task"]
        self.label: str = data["label"]
        self.family: str = data.get("family", self.id)
        self.requires: list[str] = data.get("requires", [])
        self.params: dict[str, dict] = data.get("params", {})
        self.lora_points: list[dict] = data.get("lora_points", [])
        self.outputs: list[dict] = data.get("outputs", [])
        self.tiers: dict[str, dict] = data.get("tiers", {})
        self.fallback: list[str] = data.get("fallback", [])
        self.description: str = data.get("description", "")
        self.badges: list[str] = data.get("badges", [])
        self.template_file: Path = template_dir / "workflow_api.json"

    def load_workflow(self) -> dict[str, Any]:
        return json.loads(self.template_file.read_text("utf-8"))

    def to_api_dict(self, available: bool = True, unavailable_reason: str = "") -> dict:
        return {
            "id": self.id,
            "task": self.task,
            "label": self.label,
            "family": self.family,
            "description": self.description,
            "badges": self.badges,
            "requires": self.requires,
            "params": self.params,
            "tiers": self.tiers,
            "lora_points": self.lora_points,
            "available": available,
            "unavailable_reason": unavailable_reason,
        }


class PipelineRegistry:
    def __init__(self) -> None:
        self._manifests: dict[str, PipelineManifest] = {}
        self._availability: dict[str, tuple[bool, str]] = {}  # id -> (ok, reason)

    def load_all(self) -> None:
        """Scan templates directory and load every manifest.yaml."""
        self._manifests.clear()
        if not TEMPLATES_DIR.exists():
            logger.warning("Templates dir not found: %s", TEMPLATES_DIR)
            return
        for subdir in sorted(TEMPLATES_DIR.iterdir()):
            mf = subdir / "manifest.yaml"
            wf = subdir / "workflow_api.json"
            if not (mf.exists() and wf.exists()):
                continue
            try:
                data = yaml.safe_load(mf.read_text("utf-8"))
                manifest = PipelineManifest(data, subdir)
                self._manifests[manifest.id] = manifest
                logger.info("Loaded pipeline: %s", manifest.id)
            except Exception as e:
                logger.error("Failed to load pipeline %s: %s", subdir.name, e)

    def required_model_files(self, mf: PipelineManifest) -> list[str]:
        """Model filenames referenced by the workflow's loader nodes."""
        try:
            workflow = mf.load_workflow()
        except Exception:
            return []
        names: list[str] = []
        for node in workflow.values():
            for key in _MODEL_INPUT_KEYS:
                val = (node.get("inputs") or {}).get(key)
                if isinstance(val, str) and val and val not in names:
                    names.append(val)
        return names

    def _missing_models(self, mf: PipelineManifest, installed: set[str]) -> list[str]:
        missing = [n for n in self.required_model_files(mf) if Path(n).name not in installed]
        for req in mf.requires:
            if not (Path(req).name in installed or any(req in f for f in installed)):
                missing.append(req)
        return missing

    def _installed_model_files(self) -> set[str]:
        models_dir = get_settings().models_dir
        if not models_dir.exists():
            return set()
        return {p.name for p in models_dir.rglob("*") if p.is_file()}

    def validate_models(self) -> None:
        """Mark pipelines unavailable when their model files are not on disk."""
        installed = self._installed_model_files()
        for pid, mf in self._manifests.items():
            missing = self._missing_models(mf, installed)
            if missing:
                self._availability[pid] = (False, f"Models not installed: {', '.join(missing)}")
            else:
                self._availability[pid] = (True, "")

    async def validate_against_engine(self, object_info: dict) -> None:
        """Layer node-class checks on top of the model-file check."""
        self.validate_models()
        known_classes = set(object_info.keys())

        for pid, mf in self._manifests.items():
            try:
                workflow = mf.load_workflow()
            except Exception as e:
                self._availability[pid] = (False, f"Cannot load workflow: {e}")
                continue

            missing_classes = set()
            for node in workflow.values():
                cls = node.get("class_type", "")
                if cls and cls not in known_classes:
                    missing_classes.add(cls)

            if missing_classes:
                self._availability[pid] = (
                    False,
                    f"Missing ComfyUI nodes: {', '.join(sorted(missing_classes))}",
                )

    def get_all(self) -> list[dict]:
        return [
            mf.to_api_dict(*self._availability.get(pid, (True, "")))
            for pid, mf in self._manifests.items()
        ]

    def get(self, pipeline_id: str) -> PipelineManifest | None:
        return self._manifests.get(pipeline_id)

    def is_available(self, pipeline_id: str) -> tuple[bool, str]:
        return self._availability.get(pipeline_id, (True, ""))


# module-level singleton
pipeline_registry = PipelineRegistry()
