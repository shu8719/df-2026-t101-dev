"""MapAnything の実験のテスト（docs/depth-scale-mapanything/scripts.md §4）。本物の重みや写真は使わない"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mapanything_backend as mab  # noqa: E402
from mapanything_backend import dp  # noqa: E402
import try_image_mapanything as tim  # noqa: E402

W, H = 640, 480


def hand_points() -> list[list[float]]:
    # 画素の中心の取り方の違いが長さに出ないよう、整数の座標にする
    pts = [[320.0, 400.0] for _ in range(21)]
    pts[5], pts[9], pts[13], pts[17] = [260.0, 250.0], [320.0, 240.0], [360.0, 245.0], [400.0, 260.0]
    return pts


def test_non_commercial_weights_are_rejected():
    with pytest.raises(SystemExit):
        mab.MapAnythingBackend("facebook/map-anything")


def test_focal_to_original():
    # 1280×720 を 518×294 にするなら、覆うように縮める割合は max(518/1280, 294/720)
    s = max(518 / 1280, 294 / 720)
    assert mab.focal_to_original(400.0, (1280, 720), (518, 294)) == pytest.approx(400.0 / s)


def test_measure_with_constant_backend():
    r = mab.ConstantBackend().infer(np.zeros((H, W, 3), np.uint8))
    L, Ld, zs = tim.measure(r, hand_points(), 3.0)
    pts = hand_points()
    for k, (a, b) in dp.SEGMENTS.items():
        expected = math.dist(pts[a], pts[b]) * 300.0 / r.f_px
        assert L[k] == pytest.approx(expected, abs=0.05)
        assert Ld[k] == pytest.approx(expected, abs=0.05)
    assert zs[0] == pytest.approx(300.0)


def test_deviation_two_percent():
    L = {k: v * 1.02 for k, v in tim.TRUTH.items()}
    assert dp.deviation_pct(dp.scale_ratio(L, tim.TRUTH)) == pytest.approx(2.0)


def test_save_images(tmp_path, monkeypatch):
    monkeypatch.setattr(mab, "DATA", tmp_path)
    rgb = np.full((H, W, 3), 128, np.uint8)
    r = mab.ConstantBackend().infer(rgb)
    pts = hand_points()
    L, _, zs = tim.measure(r, pts, 3.0)
    paths = tim.save_images("photo", r, pts, zs, L, tim.TRUTH)
    assert set(paths) == {"1_input", "2_depth", "3_conf", "4_mask", "5_side", "6_result", "grid"}
    for p in paths.values():
        assert cv2.imread(str(p)) is not None
