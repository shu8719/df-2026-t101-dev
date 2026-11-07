"""Depth Anything 3 の実験のテスト（docs/depth-scale-da3/scripts.md §7）。本物の重みや写真は使わない"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import da3_backend as db  # noqa: E402
from da3_backend import dp  # noqa: E402
import focal_sources as fs  # noqa: E402
import try_image_da3 as tid  # noqa: E402


# ---------- 計算 ----------

def test_metric_depth_formula():
    # 出力 1.0、焦点距離 300px（DA3 が見た画像の px）→ 1.0 × 300 ÷ 300 = 1m = 1000mm
    assert db.metric_depth_mm(np.array([1.0]), 300.0)[0] == pytest.approx(1000.0)


def test_focal_for_processed():
    # 元の画像 1280×720 で f=1000px、DA3 が見た画像 504×280 → (1000×504/1280 + 1000×280/720) ÷ 2
    f = db.focal_for_processed(1000.0, (1280, 720), (504, 280))
    assert f == pytest.approx((1000 * 504 / 1280 + 1000 * 280 / 720) / 2)


def test_focal_roundtrip():
    K = np.array([[db.focal_for_processed(900.0, (904, 1280), (350, 504)), 0, 175], [0, 0, 252], [0, 0, 1]], float)
    K[1, 1] = K[0, 0]
    # 縦横の比がほぼ同じなら、元の画像の px に戻すと 900px に近い
    assert db.focal_to_original(K, (904, 1280), (350, 504)) == pytest.approx(900.0, rel=0.01)


def test_scale_focal_between_image_sizes():
    assert fs.scale_focal(1000.0, (1280, 720), (640, 360)) == pytest.approx(500.0)


def test_non_commercial_model_is_rejected():
    with pytest.raises(SystemExit):
        db.DA3Backend("large")


def test_constant_backend_gives_300mm_for_any_focal():
    rgb = np.zeros((480, 640, 3), np.uint8)
    for f in (400.0, 800.0, 1500.0):
        r = db.ConstantBackend().metric(rgb, f)
        assert r.depth_mm.shape == (480, 640)
        assert float(np.median(r.depth_mm)) == pytest.approx(300.0, rel=1e-4)
        assert r.proc_wh[0] % 14 == 0 and r.proc_wh[1] % 14 == 0 and max(r.proc_wh) in (504, 490, 518)


# ---------- 出どころと流れ ----------

W, H = 640, 480


def hand_points() -> list[list[float]]:
    pts = [[320.0, 400.0] for _ in range(21)]
    pts[5], pts[9], pts[13], pts[17] = [260.0, 250.0], [320.0, 240.0], [360.0, 245.0], [400.0, 260.0]
    return pts


@pytest.fixture()
def fake_results(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "REPO_EXP", tmp_path)
    stem = "photo"
    pts = hand_points()
    dp.save_json(tmp_path / "depth_scale" / "data" / "vis" / f"{stem}_depthpro.json",
                 {"width": W * 2, "height": H * 2, "f_px": 1600.0, "z_mm": {}, "lengths_mm": {}})
    moge_len = {k: math.dist(pts[a], pts[b]) for k, (a, b) in dp.SEGMENTS.items()}
    dp.save_json(tmp_path / "depth_scale_moge2" / "data" / "vis" / f"{stem}_moge2_vitl.json",
                 {"width": W, "height": H, "f_px": 700.0, "z_mm": {str(p): 600.0 for p in dp.DEPTH_POINTS},
                  "lengths_mm": moge_len})
    return stem


def test_image_focal_scales_to_given_size(fake_results):
    # Depth Pro の JSON は 2倍の大きさの画像で f=1600px → この大きさでは 800px
    assert fs.image_focal("depthpro", fake_results, (W, H)) == pytest.approx(800.0)


def test_missing_source_stops_with_message(fake_results):
    with pytest.raises(SystemExit):
        fs.image_focal("moge2vits", fake_results, (W, H))


def test_combo_da3_with_focal(fake_results):
    rgb = np.zeros((H, W, 3), np.uint8)
    r = tid.run_combo("da3+depthpro", rgb, hand_points(), fake_results, db.ConstantBackend(), None, 3.0, 0.0)
    pts = hand_points()
    for k, (a, b) in dp.SEGMENTS.items():  # 深度300mm、焦点距離800px
        assert r["lengths_mm"][k] == pytest.approx(math.dist(pts[a], pts[b]) * 300.0 / 800.0, rel=1e-3)


def test_combo_shape_times_scale(fake_results):
    # MoGe-2 の距離 600mm、DA3 の深度 300mm → 倍率 0.5、長さは MoGe-2 の半分
    rgb = np.zeros((H, W, 3), np.uint8)
    r = tid.run_combo("moge2vitl*da3", rgb, hand_points(), fake_results, db.ConstantBackend(), None, 3.0, 0.0)
    pts = hand_points()
    assert r["scale"] == pytest.approx(0.5, rel=1e-3)
    for k, (a, b) in dp.SEGMENTS.items():
        assert r["lengths_mm"][k] == pytest.approx(0.5 * math.dist(pts[a], pts[b]), rel=1e-3)


def test_combo_da3base(fake_results):
    rgb = np.zeros((H, W, 3), np.uint8)
    be = db.ConstantBackend()
    r = tid.run_combo("da3+da3base", rgb, hand_points(), fake_results, be, be, 3.0, 0.0)
    assert r["f_px"] == pytest.approx(dp.f_px_from_35mm(26.0, W, H))
