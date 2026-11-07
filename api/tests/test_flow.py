"""APIの流れを最後まで（OpenSCADが入っている環境で動く）。"""
import shutil

import pytest
from fastapi.testclient import TestClient

from app import scad_runner, store
from app.main import app

needs_openscad = pytest.mark.skipif(not shutil.which(scad_runner.openscad_bin()) and not __import__("pathlib").Path(scad_runner.openscad_bin()).exists(),
                                    reason="OpenSCADがない")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "CASES", tmp_path / "cases")
    monkeypatch.setattr(store, "FILES", tmp_path / "files")
    return TestClient(app)


REQ = dict(activity="draw", tool_type="brush", hand_side="right", tool_shaft_size="medium",
           tool_shaft_shape="round", nut_operator="self_weak", grip_strength="light", capture_by="helper")


@needs_openscad
def test_full_flow(client):
    cid = client.post("/v1/cases", json={"title": "筆の握り"}).json()["case_id"]
    assert client.put(f"/v1/cases/{cid}/requirements", json=REQ).json()["requirements"]["tool_shaft_diameter_mm"] == 10
    assert client.post(f"/v1/cases/{cid}/interview", json={"message": "指を伸ばす装具がほしい"}).json()["turn"]["status"] == "out_of_scope"
    m = client.get("/v1/sample-measurement").json()
    assert client.put(f"/v1/cases/{cid}/measurement", json=m).status_code == 200
    d = client.post(f"/v1/cases/{cid}/designs", json={}).json()["design"]
    assert d["status"] == "ready" and d["variant"] == "fitted" and d["nut_variant"] == "wings"
    assert d["mesh_check"]["ok"]
    same = client.post(f"/v1/cases/{cid}/designs/{d['design_id']}/refine", json={"style": {"color": "#E8A0BF", "pattern": "none"}}).json()["design"]
    assert same["design_id"] == d["design_id"]          # 色だけなら版を作らない
    p = client.post(f"/v1/cases/{cid}/designs/{d['design_id']}/prepare-print").json()["design"]
    assert p["print_check"]["ok"] and p["print_check"]["bodies"] == 2


def test_requirements_reject_unknown_values(client):
    cid = client.post("/v1/cases", json={}).json()["case_id"]
    bad = {**REQ, "hand_side": "both"}
    assert client.put(f"/v1/cases/{cid}/requirements", json=bad).status_code == 422
