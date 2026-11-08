"""YOLO26 Depth の実験のテスト（docs/depth-scale-yolo26/scripts.md §5）。本物の重みや写真は使わない"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import calibration as cal  # noqa: E402
import focal as fc  # noqa: E402
import try_image_yolo26 as ty  # noqa: E402
from yolo26_backend import dp  # noqa: E402


def test_focal_from_exif_uncropped():
    # 2268×4032（4:3 の 3024×4032 から左右を切った）、26mm 相当、長い辺 1280px に縮める → 約 961px
    f = fc.f_px_from_35mm_uncropped(26.0, 4032, 1280)
    assert f == pytest.approx(26.0 * 4032 * math.sqrt(1 + 0.75 ** 2) / 43.27 * 1280 / 4032)
    assert f == pytest.approx(961.0, abs=1.0)


def test_lengths_constant_depth():
    pts = [[320.0, 400.0] for _ in range(21)]
    pts[5], pts[9], pts[13], pts[17] = [260.0, 250.0], [320.0, 240.0], [360.0, 245.0], [400.0, 260.0]
    L, zs = ty.lengths(np.full((480, 640), 300.0, np.float32), pts, 800.0)
    for k, (a, b) in dp.SEGMENTS.items():
        assert L[k] == pytest.approx(math.dist(pts[a], pts[b]) * 300.0 / 800.0, rel=1e-3)
    assert zs[0] == pytest.approx(300.0)


def test_leave_one_out_constant_bias_is_removed():
    per = {f"p{i}": {k: v * 1.30 for k, v in cal.TRUTH.items()} for i in range(5)}
    r = cal.evaluate(per, set())
    assert r["raw_med"] == pytest.approx(30.0)
    assert r["corr_med"] == pytest.approx(0.0, abs=1e-9) and r["pass"]


def test_leave_one_out_varying_bias_fails():
    per = {"a": {k: v * 1.30 for k, v in cal.TRUTH.items()}, "b": {k: v * 1.50 for k, v in cal.TRUTH.items()}}
    r = cal.evaluate(per, set())
    assert not r["pass"] and r["corr_med"] > 10
