import io
import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

os.environ["HAND_MESH_BACKEND"] = "mock"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

import angles  # noqa: E402
from app import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _jpeg(color, size=(64, 48)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def _post(client, meta, n_frames=2, headers=None):
    files = {"meta": (None, json.dumps(meta), "application/json")}
    for i in range(n_frames):
        files[f"frame_{i}"] = (f"frame_{i}.jpg", _jpeg((200, 150 + i * 20, 120)), "image/jpeg")
    return client.post("/v1/angles", files=files, headers=headers or {"X-User": "u_test"})


META = {"case_id": "c_test", "consent": True, "hand_side": "right",
        "frames": [{"name": "frame_0", "view": "thumb_side"}, {"name": "frame_1", "view": "top"}]}


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["backend"] == "mock" and body["model_loaded"] is True
    assert "device" in body


def test_consent_required(client):
    r = _post(client, {**META, "consent": False})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "CONSENT_REQUIRED" and err["retryable"] is False and err["message"]


def test_consent_missing(client):
    meta = {k: v for k, v in META.items() if k != "consent"}
    assert _post(client, meta).json()["error"]["code"] == "CONSENT_REQUIRED"


@pytest.mark.parametrize("side", ["right", "left"])
def test_success_schema(client, side):
    r = _post(client, {**META, "hand_side": side})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["method"] == "mesh_recovery"
    assert body["model"] == "mock"
    assert body["warnings"] == []
    assert set(body["fingers"]) == {"index", "middle", "ring", "pinky"}
    for f in body["fingers"].values():
        assert set(f) == {"flexion_deg", "iqr_deg", "frames_used"}
        assert f["frames_used"] == 2
        for key in ("flexion_deg", "iqr_deg"):
            assert set(f[key]) == {"mcp", "pip", "dip"}
            assert all(isinstance(v, float) for v in f[key].values())
        assert all(0 < v < 120 for v in f["flexion_deg"].values())
        assert all(v >= 0 for v in f["iqr_deg"].values())


def test_mock_deterministic(client):
    a = _post(client, META).json()
    b = _post(client, META).json()
    assert a == b


def test_cors_localhost(client):
    r = client.options("/v1/angles", headers={"Origin": "http://localhost:5173",
                                              "Access-Control-Request-Method": "POST",
                                              "Access-Control-Request-Headers": "x-user"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
    r = client.options("/v1/angles", headers={"Origin": "https://evil.example.com",
                                              "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in r.headers


def test_bad_requests(client):
    assert _post(client, {**META, "hand_side": "both"}).status_code == 400
    assert _post(client, META, n_frames=0).json()["error"]["code"] == "INVALID_ARGUMENT"
    r = client.post("/v1/angles", files={"meta": (None, json.dumps(META)),
                                         "frame_0": ("a.jpg", b"not a jpeg", "image/jpeg")})
    assert r.status_code == 400


def test_sam3d_strict_missing_weights(client, monkeypatch, tmp_path):
    """HAND_MESH_BACKEND=sam3d without weights: no mock fallback, 503 MESH_UNAVAILABLE + reason in /healthz."""
    from backends import BackendManager

    monkeypatch.setenv("HAND_MESH_CHECKPOINT_DIR", str(tmp_path))  # empty dir -> missing files
    mgr = BackendManager("sam3d")
    mgr.start(background=False)
    old = client.app.state.backends
    client.app.state.backends = mgr
    try:
        h = client.get("/healthz").json()
        assert h["ok"] is False and h["model_loaded"] is False
        assert h["sam3d"]["status"] == "failed" and h["sam3d"]["reason"]
        r = _post(client, META)
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "MESH_UNAVAILABLE" and r.json()["error"]["retryable"] is True
    finally:
        client.app.state.backends = old


# --- angle math -------------------------------------------------------------

def _rand_rot(seed):
    q, _ = np.linalg.qr(np.random.default_rng(seed).normal(size=(3, 3)))
    return q * np.sign(np.linalg.det(q))  # proper rotation


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_angle_roundtrip(seed):
    """FK (measurement.md §8.2) -> keypoints in any camera pose -> same angles, incl. hyperextension."""
    want = {"index": {"mcp": 10.0, "pip": 85.0, "dip": -12.0},
            "middle": {"mcp": 45.0, "pip": 60.0, "dip": 20.0},
            "ring": {"mcp": 70.0, "pip": 30.0, "dip": 5.0},
            "pinky": {"mcp": -15.0, "pip": 100.0, "dip": 40.0}}
    kps = angles.synthetic_right_keypoints(want, _rand_rot(seed))
    got = angles.frame_flexion(angles.to_canonical_left(kps))
    for f in want:
        for j in want[f]:
            assert got[f][j] == pytest.approx(want[f][j], abs=1e-6)


def test_aggregate_median_iqr():
    fr = [{f: {"mcp": v, "pip": v, "dip": v} for f in angles.FINGERS} for v in (10.0, 20.0, 30.0, 40.0)]
    out = angles.aggregate(fr)
    assert out["index"]["flexion_deg"]["mcp"] == 25.0
    assert out["index"]["iqr_deg"]["mcp"] == 15.0
    assert out["index"]["frames_used"] == 4
