"""
Tests for the model catalog YAML.
"""
import pytest
from pathlib import Path
import yaml


CATALOG_PATH = Path(__file__).parents[1] / "app" / "models_mgr" / "catalog.yaml"


def test_catalog_exists():
    assert CATALOG_PATH.exists()


def test_catalog_is_valid_yaml():
    data = yaml.safe_load(CATALOG_PATH.read_text("utf-8"))
    assert isinstance(data, dict)
    assert len(data) > 0


def test_catalog_entries_have_required_fields():
    data = yaml.safe_load(CATALOG_PATH.read_text("utf-8"))
    for cat_id, entry in data.items():
        assert "filename" in entry, f"{cat_id}: missing 'filename'"
        assert "folder" in entry, f"{cat_id}: missing 'folder'"
        assert "license" in entry, f"{cat_id}: missing 'license'"
        assert "pack" in entry, f"{cat_id}: missing 'pack'"
        assert entry["pack"] in ("starter", "quality", "extra"), f"{cat_id}: unknown pack '{entry['pack']}'"


def test_catalog_no_duplicate_filenames():
    data = yaml.safe_load(CATALOG_PATH.read_text("utf-8"))
    seen = {}
    for cat_id, entry in data.items():
        key = (entry.get("folder", ""), entry["filename"])
        if key in seen:
            pytest.fail(f"Duplicate file {key} in entries {seen[key]} and {cat_id}")
        seen[key] = cat_id
