"""
Tests for manifest loading and pipeline registry.
"""
import pytest
from pathlib import Path
from app.pipelines.registry import PipelineManifest, TEMPLATES_DIR


def test_templates_dir_exists():
    assert TEMPLATES_DIR.exists(), f"Templates dir not found: {TEMPLATES_DIR}"


def test_all_templates_have_both_files():
    for subdir in TEMPLATES_DIR.iterdir():
        if not subdir.is_dir():
            continue
        assert (subdir / "manifest.yaml").exists(), f"Missing manifest.yaml in {subdir.name}"
        assert (subdir / "workflow_api.json").exists(), f"Missing workflow_api.json in {subdir.name}"


def test_manifests_have_required_fields():
    import yaml
    for subdir in TEMPLATES_DIR.iterdir():
        mf_path = subdir / "manifest.yaml"
        if not mf_path.exists():
            continue
        data = yaml.safe_load(mf_path.read_text("utf-8"))
        assert "id" in data, f"{subdir.name}: missing 'id'"
        assert "task" in data, f"{subdir.name}: missing 'task'"
        assert "label" in data, f"{subdir.name}: missing 'label'"
        assert "params" in data, f"{subdir.name}: missing 'params'"


def test_manifest_workflow_is_valid_json():
    import json
    for subdir in TEMPLATES_DIR.iterdir():
        wf_path = subdir / "workflow_api.json"
        if not wf_path.exists():
            continue
        try:
            graph = json.loads(wf_path.read_text("utf-8"))
        except json.JSONDecodeError as e:
            pytest.fail(f"{subdir.name}/workflow_api.json is not valid JSON: {e}")
        # Every node must have class_type
        for node_id, node in graph.items():
            assert "class_type" in node, f"{subdir.name}: node {node_id} missing class_type"


def test_registry_loads_all():
    from app.pipelines.registry import pipeline_registry
    pipeline_registry.load_all()
    pipelines = pipeline_registry.get_all()
    # We expect at least these:
    expected_ids = {
        "flux2_klein_4b_i2i", "flux2_klein_9b_i2i",
        "wan22_5b_i2v", "wan22_a14b_i2v",
        "wan22_5b_t2v", "zimage_turbo_t2i",
        "upscale_image_esrgan", "interpolate_rife",
    }
    found = {p["id"] for p in pipelines}
    missing = expected_ids - found
    assert not missing, f"Missing pipelines: {missing}"
