"""③ depth.py と ④ measure.py の流れを、重みなしの偽物（深度300mm一定）で通すテスト"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common  # noqa: E402
import depth  # noqa: E402
import measure  # noqa: E402

W, H = 640, 480


def hand_points(dx: float = 0.0) -> list[list[float]]:
    """21点。手首と付け根だけ意味のある位置に置き、ほかは手首の近くに置く"""
    pts = [[320.0 + dx, 400.0]] * 21
    pts = [list(p) for p in pts]
    pts[5] = [260.0 + dx, 250.0]
    pts[9] = [320.0 + dx, 240.0]
    pts[13] = [360.0 + dx, 245.0]
    pts[17] = [400.0 + dx, 260.0]
    return pts


@pytest.fixture()
def data(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "DATA", tmp_path)
    rid = "p1_t1"
    fdir = tmp_path / "frames" / rid
    fdir.mkdir(parents=True)
    frames, lms = [], []
    for i in range(5):
        cv2.imwrite(str(fdir / f"{i:03d}.jpg"), np.full((H, W, 3), 128, np.uint8))
        frames.append({"index": i, "t_s": i / 3, "width": W, "height": H, "blur": 1.0})
        lms.append({"index": i, "used": True, "reason": "", "points_px": hand_points(dx=i)})
    common.save_json(fdir / "frames.json", {"rec_id": rid, "frames": frames})
    common.save_json(tmp_path / "landmarks" / f"{rid}.json", {"rec_id": rid, "frames": lms})
    common.write_csv(tmp_path / "recordings.csv", [{"rec_id": rid, "person": "p1", "focal_35mm_mm": "26"}],
                     ["rec_id", "person", "focal_35mm_mm"])
    return rid


def expected(a: int, b: int, f: float) -> float:
    pts = hand_points()
    return math.dist(pts[a], pts[b]) * 300.0 / f


@pytest.mark.parametrize("cond", ["A", "B", "C"])
def test_constant_depth_lengths(data, cond):
    depth.run(data, cond, depth.ConstantBackend(), force=True)
    rows = measure.measure(data, cond, [3.0], [0.0])
    row = next(r for r in rows if r["subset"] == "all")
    assert row["status"] == "ok" and row["frames_used"] == 5
    f = row["f_px_median"]
    if cond in ("A", "C"):
        assert f == pytest.approx(common.f_px_from_35mm(26.0, W, H), abs=0.01)  # 出力は小数2桁に丸める
    for k, (a, b) in common.SEGMENTS.items():
        assert row[k] == pytest.approx(expected(a, b, f), abs=0.02)


def test_cond_b_has_8_frame_subset(data):
    depth.run(data, "B", depth.ConstantBackend(), force=True)
    rows = measure.measure(data, "B", [3.0], [0.0])
    assert {r["subset"] for r in rows} == {"all", "8"}


def test_compare_end_to_end(data, tmp_path):
    import compare

    depth.run(data, "A", depth.ConstantBackend(), force=True)
    rows = measure.measure(data, "A", [3.0], [0.0])
    common.write_csv(tmp_path / "results" / "lengths.csv", rows, measure.FIELDS)
    row = rows[0]
    # ノギスの正解を、AIの長さのちょうど 1/1.02 にする → ずれ +2.0%
    truth = {k: row[k] / 1.02 for k in common.SEGMENTS}
    common.write_csv(tmp_path / "truth.csv", [{"person": "p1", **truth}], ["person", *common.SEGMENTS])
    coin = {"palm": {v: truth[k] for k, v in compare.COIN_KEYS.items()}}
    common.save_json(tmp_path / "coin" / f"{data}.json", coin)
    compare.main([])
    out = {r["method"]: r for r in common.read_csv(tmp_path / "results" / "summary.csv")}
    assert float(out["1円玉"]["deviation_pct"]) == pytest.approx(0.0, abs=0.01)
    assert float(out["A"]["deviation_pct"]) == pytest.approx(2.0, abs=0.01)
    assert (tmp_path / "results" / "summary.md").exists() and (tmp_path / "results" / "meta.json").exists()


def test_skin_offset_scales_lengths(data):
    depth.run(data, "A", depth.ConstantBackend(), force=True)
    base, off = measure.measure(data, "A", [3.0], [0.0, 30.0])
    # 深度に30mm足すと、長さは 330/300 倍になる
    assert off["seg_5_17_mm"] / base["seg_5_17_mm"] == pytest.approx(330.0 / 300.0, rel=1e-3)
