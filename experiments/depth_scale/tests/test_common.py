"""計算のテスト（docs/depth-scale/scripts.md §8）。本物の動画やモデルは使わない"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common  # noqa: E402


def test_backproject_plane_50mm():
    # カメラから300mmの平らな面の上で、50mm離れた2点を f=1000px で写す
    f, cx, cy, z = 1000.0, 640.0, 360.0, 300.0
    u1, u2 = cx + (-25.0) * f / z, cx + 25.0 * f / z
    p1 = common.backproject(u1, cy, z, f, cx, cy)
    p2 = common.backproject(u2, cy, z, f, cx, cy)
    assert np.linalg.norm(p1 - p2) == pytest.approx(50.0, abs=0.01)


def test_f_px_from_35mm():
    assert common.f_px_from_35mm(26.0, 1280, 720) == pytest.approx(26.0 * math.hypot(1280, 720) / 43.27)


def test_f_crop_to_orig():
    # 切り抜きの長い辺640px を512pxに縮めた画像で f=400px → 元のフレームでは 500px
    assert common.f_crop_to_orig(400.0, 640.0) == pytest.approx(500.0)


def test_patch_depth_ignores_outliers():
    patch = np.full((31, 31), 300.0, dtype=np.float32)
    patch[15, 15] = np.inf
    patch[15, 16] = 0.0
    patch[16, 15] = np.nan
    patch[14, 15] = 310.0
    assert common.patch_depth(patch, 3) == pytest.approx(300.0)


def test_patch_depth_all_invalid():
    assert common.patch_depth(np.full((31, 31), np.nan, dtype=np.float32), 3) is None


def test_extract_patch_pads_outside():
    depth = np.arange(100, dtype=np.float32).reshape(10, 10)
    p = common.extract_patch(depth, 0, 0, size=5)
    assert np.isnan(p[0, 0]) and p[2, 2] == 0.0 and p[4, 4] == depth[2, 2]


def test_top_median_10_frames():
    # 10枚の20%は2枚で最低の3枚に足りないので、上位3枚（10・9・8）の中央値
    assert common.top_median([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]) == 9


def test_top_median_20_frames():
    # 20枚の20%は4枚。上位4枚（20・19・18・17）の中央値
    assert common.top_median(list(range(1, 21))) == pytest.approx(18.5)


def test_deviation_from_ratio():
    truth = {k: 50.0 for k in common.SEGMENTS}
    lengths = {k: 51.0 for k in common.SEGMENTS}
    assert common.deviation_pct(common.scale_ratio(lengths, truth)) == pytest.approx(2.0)


def test_loo_corrected_removes_common_bias():
    ratios = {"p1": [0.96, 0.96], "p2": [0.96], "p3": [0.96]}
    corr = common.loo_corrected(ratios)
    for rs in corr.values():
        for r in rs:
            assert common.deviation_pct(r) == pytest.approx(0.0)


def test_loo_corrected_single_person_is_nan():
    assert math.isnan(common.loo_corrected({"p1": [0.98]})["p1"][0])


def test_crop_box_matches_app():
    pts = [[100, 200], [300, 400]]
    assert common.crop_box(pts, 1280, 720) == (60.0, 160.0, 340.0, 440.0)
    assert common.crop_box([[10, 10], [110, 110]], 100, 100) == (0.0, 0.0, 100.0, 100.0)


def test_even_subset():
    assert common.even_subset(list(range(5)), 8) == [0, 1, 2, 3, 4]
    s = common.even_subset(list(range(30)), 8)
    assert len(s) == 8 and s[0] == 0 and s[-1] == 29
