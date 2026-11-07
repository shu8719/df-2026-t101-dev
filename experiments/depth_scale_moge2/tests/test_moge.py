"""MoGe-2 の実験のテスト（docs/depth-scale-moge2/scripts.md §7）。本物の重みや動画は使わない"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import moge_backend as mb  # noqa: E402
from moge_backend import dp  # noqa: E402
import depth_moge  # noqa: E402
import measure_moge  # noqa: E402

W, H = 640, 480


# ---------- 計算 ----------

def test_patch_point_ignores_invalid():
    pts = np.zeros((31, 31, 3), np.float32)
    pts[..., 0], pts[..., 1], pts[..., 2] = 10.0, 20.0, 300.0
    pts[15, 15] = np.inf
    pts[15, 16] = [999, 999, 999]
    mask = np.ones((31, 31), np.float32)
    mask[15, 16] = 0.0
    assert mb.patch_point(pts, mask, 3) == pytest.approx([10.0, 20.0, 300.0])


def test_patch_point_none_when_all_invalid():
    assert mb.patch_point(np.full((31, 31, 3), np.inf, np.float32), None, 3) is None


def test_fov_from_f_px():
    assert mb.fov_x_from_f_px(1000.0, 1280) == pytest.approx(math.degrees(2 * math.atan(640 / 1000)))


def test_f_px_from_normalized_intrinsics():
    # MoGe の正規化：fx は幅を1、fy は高さを1とした焦点距離。f_px = fx×幅 = fy×高さ
    f = 900.0
    intr = np.array([[f / 1280, 0, 0.5], [0, f / 720, 0.5], [0, 0, 1]])
    assert mb.f_px_from_normalized(intr, 1280, 720) == pytest.approx(900.0)


def test_moge_focal_formula_roundtrip():
    # MoGe の infer の式：画角から focal（対角線の半分を1とした値）を出し、fx・fy に直す。px に直すと W/(2·tan(fov/2)) になる
    w, h, fov = 1280, 720, 60.0
    a = w / h
    focal = a / math.sqrt(1 + a * a) / math.tan(math.radians(fov) / 2)
    fx = focal / 2 * math.sqrt(1 + a * a) / a
    fy = focal / 2 * math.sqrt(1 + a * a)
    intr = np.array([[fx, 0, 0.5], [0, fy, 0.5], [0, 0, 1]])
    assert mb.f_px_from_normalized(intr, w, h) == pytest.approx(w / (2 * math.tan(math.radians(fov) / 2)))


def test_push_out():
    p = np.array([0.0, 0.0, 300.0])
    assert mb.push_out(p, 30.0) == pytest.approx([0.0, 0.0, 330.0])


# ---------- 流れ（偽物の平らな面） ----------

def hand_points() -> list[list[float]]:
    # 画素の中心の取り方の違いが長さに出ないよう、整数の座標にする
    pts = [[320.0, 400.0] for _ in range(21)]
    pts[5], pts[9], pts[13], pts[17] = [260.0, 250.0], [320.0, 240.0], [360.0, 245.0], [400.0, 260.0]
    return pts


@pytest.fixture()
def data(tmp_path, monkeypatch):
    dp_data = tmp_path / "dp"
    mg_data = tmp_path / "mg"
    monkeypatch.setattr(dp, "DATA", dp_data)
    monkeypatch.setattr(mb, "DATA", mg_data)
    rid = "p1_t1"
    fdir = dp_data / "frames" / rid
    fdir.mkdir(parents=True)
    frames, lms = [], []
    for i in range(5):
        cv2.imwrite(str(fdir / f"{i:03d}.jpg"), np.full((H, W, 3), 128, np.uint8))
        frames.append({"index": i, "t_s": i / 3, "width": W, "height": H, "blur": 1.0})
        lms.append({"index": i, "used": True, "reason": "", "points_px": hand_points()})
    dp.save_json(fdir / "frames.json", {"rec_id": rid, "frames": frames})
    dp.save_json(dp_data / "landmarks" / f"{rid}.json", {"rec_id": rid, "frames": lms})
    dp.write_csv(dp_data / "recordings.csv", [{"rec_id": rid, "person": "p1", "focal_35mm_mm": "26"}],
                 ["rec_id", "person", "focal_35mm_mm"])
    return rid


@pytest.mark.parametrize("cond", ["A", "B", "C"])
def test_constant_points_and_depth_agree(data, cond):
    depth_moge.run(data, "constant", cond, mb.ConstantBackend(), force=True)
    rows = measure_moge.measure(data, "constant", cond, [3.0], [0.0])
    by = {(r["source"], r["subset"]): r for r in rows}
    f_expected = dp.f_px_from_35mm(26.0, W, H)
    pts = hand_points()
    for source in ("points", "depth"):
        row = by[(source, "all")]
        assert row["status"] == "ok" and row["frames_used"] == 5
        if cond != "B":
            assert row["f_px_median"] == pytest.approx(f_expected, abs=0.01)
        f = row["f_px_median"]
        for k, (a, b) in dp.SEGMENTS.items():
            assert row[k] == pytest.approx(math.dist(pts[a], pts[b]) * 300.0 / f, abs=0.05)
    if cond == "B":
        assert ("points", "8") in by


@pytest.mark.parametrize("cond", ["A", "B"])
def test_save_vis_writes_frame_images(data, cond):
    depth_moge.run(data, "constant", cond, mb.ConstantBackend(), force=True, save_vis=True)
    files = sorted((mb.DATA / "vis" / data).glob(f"constant_{cond}_*.jpg"))
    assert len(files) == 5
    img = cv2.imread(str(files[0]))
    assert img is not None and img.shape[1] > img.shape[0]  # 写真と深度を横に並べている


def test_compare_all(data, tmp_path):
    import compare_all

    depth_moge.run(data, "constant", "A", mb.ConstantBackend(), force=True)
    rows = measure_moge.measure(data, "constant", "A", [3.0], [0.0])
    dp.write_csv(mb.DATA / "results" / "lengths.csv", rows, measure_moge.FIELDS)
    ref = next(r for r in rows if r["source"] == "points")
    # Depth Pro の長さは、MoGe-2 のちょうど 1.02 倍にする
    dp_row = {"rec_id": data, "cond": "A", "radius_px": 3.0, "skin_offset_mm": 0.0, "subset": "all", "status": "ok",
              **{k: ref[k] * 1.02 for k in dp.SEGMENTS}}
    dp.write_csv(dp.DATA / "results" / "lengths.csv", [dp_row], ["rec_id", "cond", "radius_px", "skin_offset_mm", "subset", "status", *dp.SEGMENTS])
    dp.write_csv(dp.DATA / "truth.csv", [{"person": "p1", **{k: ref[k] for k in dp.SEGMENTS}}], ["person", *dp.SEGMENTS])
    compare_all.main([])
    out = {r["method"]: r for r in dp.read_csv(mb.DATA / "results" / "summary_all.csv")}
    assert float(out["MoGe-2（偽物） A"]["deviation_pct"]) == pytest.approx(0.0, abs=0.01)
    assert float(out["Depth Pro A"]["deviation_pct"]) == pytest.approx(2.0, abs=0.01)
    assert (mb.DATA / "results" / "summary_all.md").exists()
