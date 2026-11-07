"""手のモデルと、くり抜きの検査の単体テスト（docs/tasks.md B6）。"""
import copy
import json
import math
from pathlib import Path

import numpy as np

from app import handmodel as hm

SAMPLE = json.loads((Path(__file__).resolve().parents[2] / "schemas" / "measurement.sample.json").read_text(encoding="utf-8"))


def test_finger_chain_straight_and_bent():
    flex0 = {"mcp": 0, "pip": 0, "dip": 0}
    j, d0, z = hm.finger_chain([0, 0], 0, [40, 20, 10], flex0)
    assert np.allclose(j[3], [0, 70, 0])                      # まっすぐなら y 方向に伸びる
    j, _, _ = hm.finger_chain([0, 0], 0, [40, 20, 10], {"mcp": 90, "pip": 0, "dip": 0})
    assert np.allclose(j[1], [0, 0, 40], atol=1e-9)           # 90度曲げると手のひら側（+z）へ


def test_sample_cavities_are_inside_and_plausible():
    model = hm.build(SAMPLE)
    for f in ("index", "pinky"):
        cav = model.cavities[f]
        assert cav.diameter_mm is not None
        assert 15 <= cav.diameter_mm <= 55
        assert cav.center_mm[2] > SAMPLE["palm"]["palm_thickness_mm"]   # 手のひらより前


def test_straight_fingers_have_no_cavity():
    m = copy.deepcopy(SAMPLE)
    for f in m["fingers"].values():
        f["flexion_deg"] = {"mcp": 10, "pip": 10, "dip": 5}
    model = hm.build(m)
    assert model.cavities["index"].diameter_mm is None
    assert "CAVITY_OPEN" in model.warnings


def test_strong_flexion_over_180_is_not_open():
    m = copy.deepcopy(SAMPLE)
    for f in m["fingers"].values():
        f["flexion_deg"] = {"mcp": 70, "pip": 90, "dip": 30}
    model = hm.build(m)
    assert model.cavities["index"].diameter_mm is not None


def test_baseline_fitted_passes_carve_check():
    model = hm.build(SAMPLE)
    b = hm.baseline_fitted(model, 10.6, 0.5)
    assert b is not None and b["press_depth_mm"] is not None
    assert b["carve"]["ok"]
    assert b["carve"]["min_wall_mm"] >= 3.0


def test_carve_report_detects_deep_and_thin():
    # 軸の近くを通る太いカプセル：くり抜きが深すぎ、壁も薄い
    caps = [[0, 6, 10, 0, 6, 40, 9.0]]
    rep = hm.carve_report(caps, 30, 30, 50, 11.1, 0.5)
    assert not rep["ok"]
    assert set(rep["problems"]) == {"CARVE_TOO_DEEP", "WALL_TOO_THIN"}
    # 遠くを通るカプセル：くり抜かない
    rep = hm.carve_report([[0, 40, 10, 0, 40, 40, 8.0]], 30, 30, 50, 11.1, 0.5)
    assert rep["ok"] and rep["max_depth_mm"] == 0


def test_grip_frame_is_right_handed():
    model = hm.build(SAMPLE)
    fr = hm.grip_frame(model, 12)
    r = fr.rotation
    assert math.isclose(np.linalg.det(r), 1.0, abs_tol=1e-6)
