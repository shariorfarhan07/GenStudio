"""Every model filename referenced by a template loader exists in the catalog (no network)."""
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1] / "app"
CATALOG = yaml.safe_load((ROOT / "models_mgr" / "catalog.yaml").read_text("utf-8"))
TEMPLATES = sorted((ROOT / "pipelines" / "templates").iterdir())
KEYS = ("unet_name", "clip_name", "clip_name1", "clip_name2", "vae_name", "model_name", "lora_name")
# RIFE checkpoints are auto-managed by ComfyUI-Frame-Interpolation, but we still ship rife49.pth.


@pytest.mark.parametrize("tdir", TEMPLATES, ids=lambda p: p.name)
def test_template_filenames_in_catalog(tdir):
    wf = json.loads((tdir / "workflow_api.json").read_text("utf-8"))
    filenames = {e["filename"] for e in CATALOG.values()}
    for nid, node in wf.items():
        for k, v in node["inputs"].items():
            if k in KEYS or k == "ckpt_name":
                assert v in filenames, f"{tdir.name}: node {nid} {k}={v} not in catalog"


def test_catalog_urls_well_formed():
    for cid, e in CATALOG.items():
        assert e["repo"].count("/") == 1, cid
        assert e.get("path", e["filename"]).endswith(Path(e["filename"]).suffix), cid
        assert e["size_bytes"] > 0, cid


def test_flux2_and_zimage_loaders():
    for t in ("flux2_klein_4b_i2i", "flux2_klein_9b_i2i", "zimage_turbo_t2i"):
        wf = json.loads((ROOT / "pipelines" / "templates" / t / "workflow_api.json").read_text("utf-8"))
        types = {n["class_type"] for n in wf.values()}
        assert "DualCLIPLoader" not in types
        clip = next(n for n in wf.values() if n["class_type"] == "CLIPLoader")
        assert clip["inputs"]["type"] == ("lumina2" if t.startswith("zimage") else "flux2")
