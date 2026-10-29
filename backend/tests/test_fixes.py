"""
Regression tests for job creation, LoRA injection, input path safety,
LAN auth and SPA fallback.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine

from app.config import get_settings
from app.jobs.queue import _load_input_file, _is_oom, set_db_engine
from app.pipelines.patcher import _inject_loras


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app.main import app
    from app.pipelines.registry import pipeline_registry

    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(engine)
    set_db_engine(engine)
    pipeline_registry.load_all()
    for pid in list(pipeline_registry._manifests):
        pipeline_registry._availability[pid] = (True, "")
    return TestClient(app, client=("127.0.0.1", 5000))


def test_create_single_job(client):
    r = client.post("/api/jobs", json={"pipeline_id": "zimage_turbo_t2i", "params": {"prompt": "x"}})
    assert r.status_code == 200, r.text
    ids = r.json()["job_ids"]
    assert len(ids) == 1 and ids[0]
    assert client.get(f"/api/jobs/{ids[0]}").json()["status"] == "queued"


def test_variations_share_batch_id(client):
    r = client.post("/api/jobs", json={
        "pipeline_id": "zimage_turbo_t2i", "params": {"prompt": "x"},
        "batch": {"mode": "variations", "count": 3},
    })
    assert r.status_code == 200, r.text
    ids = r.json()["job_ids"]
    assert len(ids) == 3
    batches = {client.get(f"/api/jobs/{i}").json()["batch_id"] for i in ids}
    assert len(batches) == 1 and None not in batches


def test_settings_wrong_type_is_422(client):
    r = client.put("/api/settings", json={"port": "not-a-number"})
    assert r.status_code == 422


def _upstream_refs(graph, nid, seen=None):
    seen = seen or set()
    for v in graph[nid]["inputs"].values():
        if isinstance(v, list) and len(v) == 2 and str(v[0]) in graph:
            if str(v[0]) in seen:
                continue
            seen.add(str(v[0]))
            _upstream_refs(graph, str(v[0]), seen)
    return seen


@pytest.mark.parametrize("n", [1, 2])
def test_inject_loras_no_cycle(n):
    graph = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "a"}},
        "3": {"class_type": "KSampler", "inputs": {"model": ["1", 0]}},
    }
    loras = [{"file": f"l{i}.safetensors", "weight": 0.5} for i in range(n)]
    out = _inject_loras(graph, [{"after": "1"}], loras)
    lora_ids = [k for k, v in out.items() if v["class_type"] == "LoraLoaderModelOnly"]
    assert len(lora_ids) == n
    assert out["3"]["inputs"]["model"] == [lora_ids[-1], 0]
    assert out[lora_ids[0]]["inputs"]["model"] == ["1", 0]
    if n == 2:
        assert out[lora_ids[1]]["inputs"]["model"] == [lora_ids[0], 0]
    # acyclic: walking upstream from the sampler never revisits the sampler
    assert "3" not in _upstream_refs(out, "3")


def test_upload_path_traversal_rejected(tmp_path, monkeypatch):
    cfg = get_settings()
    monkeypatch.setattr(cfg, "data_dir", tmp_path)
    (tmp_path / "uploads").mkdir()
    (tmp_path / "secret.txt").write_text("nope")
    (tmp_path / "uploads" / "ok.png").write_bytes(b"png")
    with pytest.raises(ValueError):
        _load_input_file({"_upload_id": "../secret.txt"})
    data, name, _ = _load_input_file({"_upload_id": "ok.png"})
    assert data == b"png" and name == "ok.png"


def test_asset_path_must_be_in_outputs(tmp_path, monkeypatch):
    cfg = get_settings()
    out = tmp_path / "outputs"
    out.mkdir()
    monkeypatch.setattr(cfg, "outputs_dir", out)
    outside = tmp_path / "x.png"
    outside.write_bytes(b"1")
    with pytest.raises(ValueError):
        _load_input_file({"_asset_path": str(outside)})
    inside = out / "y.png"
    inside.write_bytes(b"2")
    assert _load_input_file({"_asset_path": str(inside)})[0] == b"2"


def test_oom_detection():
    assert _is_oom("CUDA out of memory. Tried to allocate")
    assert _is_oom("torch.OutOfMemoryError: x")
    assert not _is_oom("some other error")


def test_lan_middleware(client, monkeypatch):
    from app.main import app
    cfg = get_settings()
    monkeypatch.setattr(cfg, "lan_access", True)
    monkeypatch.setattr(cfg, "lan_token", "s3cret")
    remote = TestClient(app, client=("192.168.1.5", 1234))
    assert remote.get("/api/jobs").status_code == 401
    assert remote.get("/api/jobs", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert remote.get("/api/jobs", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert remote.get("/api/jobs?token=s3cret").status_code == 200
    assert client.get("/api/jobs").status_code == 200  # loopback needs no token

    monkeypatch.setattr(cfg, "lan_access", False)
    assert remote.get("/api/jobs?token=s3cret").status_code == 403


def test_spa_fallback(tmp_path, client):
    from app.main import register_spa
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>INDEX</html>")
    (dist / "assets" / "a.js").write_text("console.log(1)")
    app2 = FastAPI()

    @app2.get("/api/ping")
    async def ping():
        return {"ok": True}

    register_spa(app2, dist)
    c = TestClient(app2)
    assert "INDEX" in c.get("/gallery").text
    assert "INDEX" in c.get("/").text
    assert c.get("/assets/a.js").text == "console.log(1)"
    assert c.get("/api/ping").json() == {"ok": True}
    assert c.get("/api/missing").status_code == 404


def test_real_app_api_still_json(client):
    r = client.get("/api/jobs")
    assert r.status_code == 200 and isinstance(r.json(), list)


def test_templates_graph_integrity():
    import json
    import yaml
    from app.pipelines.registry import TEMPLATES_DIR
    for d in TEMPLATES_DIR.iterdir():
        if not (d / "manifest.yaml").exists():
            continue
        wf = json.loads((d / "workflow_api.json").read_text("utf-8"))
        mf = yaml.safe_load((d / "manifest.yaml").read_text("utf-8"))
        for nid, node in wf.items():
            for v in node["inputs"].values():
                if isinstance(v, list) and len(v) == 2 and isinstance(v[1], int):
                    assert str(v[0]) in wf, f"{d.name}: node {nid} -> missing {v[0]}"
        for pname, pm in mf["params"].items():
            refs = [pm["node"]] if "node" in pm else []
            refs += [r.split(".")[0] for r in pm.get("nodes", [])]
            for r in refs:
                assert str(r) in wf, f"{d.name}: param {pname} -> missing node {r}"
        for o in mf.get("outputs", []):
            assert str(o["node"]) in wf, f"{d.name}: output node missing"
        for lp in mf.get("lora_points", []):
            assert str(lp["after"]) in wf


def test_model_requirements_derived_from_workflow(tmp_path, monkeypatch):
    from app.pipelines.registry import pipeline_registry
    cfg = get_settings()
    monkeypatch.setattr(cfg, "models_dir", tmp_path)
    pipeline_registry.load_all()
    pipeline_registry.validate_models()
    ok, reason = pipeline_registry.is_available("wan22_5b_i2v")
    assert not ok and "wan2.2_vae.safetensors" in reason
    (tmp_path / "vae").mkdir()
    for n in ("wan2.2_vae.safetensors", "wan2.2_ti2v_5B_fp16.safetensors", "umt5_xxl_fp8_e4m3fn_scaled.safetensors"):
        (tmp_path / "vae" / n).write_bytes(b"x")
    pipeline_registry.validate_models()
    assert pipeline_registry.is_available("wan22_5b_i2v") == (True, "")
