"""Depth Anything 3 の読み込みと推論（docs/depth-scale-da3/scripts.md §3）。

コードを読んで確かめたこと（Depth Anything 3、コミット 3d835ec、2026-11-08）：
- 画像は「長い辺を 504px に縮め、縦横を 14px の倍数に丸める」（utils/io/input_processor.py）。
  カメラの情報は、fx を幅の比、fy を高さの比で直す（_resize_ixt）。
- 出力の深度（prediction.depth）は、縮めたあとの大きさ。カメラの情報を渡さなければ、合わせ込みはされない（api.py）。
- 「÷300」の式は utils/alignment.py の apply_metric_scaling：
    実際の深度 = 出力 × ((fx + fy) / 2) ÷ 300
  fx・fy は、縮めたあとの画像の px（公式の Nested 版は、メインの枝が出した、縮めた画像のカメラの情報を使う）。
- 単位はメートルと見込む（FAQ に「metric depth」とだけある）。mm に直して返す。

したがって、元の画像の px の焦点距離 f から、出力の深度の大きさ (W_p, H_p) に合わせて
  fx_p = f × W_p ÷ W、 fy_p = f × H_p ÷ H、 f_p = (fx_p + fy_p) ÷ 2
を出し、実際の深度（m）= 出力 × f_p ÷ 300 とする。最後に元の画像の大きさに引き伸ばす。
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
DP_DIR = HERE.parent / "depth_scale"  # Depth Pro の実験のフォルダ（読むだけ）
if str(DP_DIR) not in sys.path:
    sys.path.insert(0, str(DP_DIR))

import common as dp  # noqa: E402

DATA = HERE / "data"
CHECKPOINTS = HERE / "checkpoints"

# 使ってよいモデル（Apache-2.0）だけを決め打ちにする。非営利（CC BY-NC）の版は読み込まない
MODELS = {
    "metric": "depth-anything/DA3METRIC-LARGE",
    "base": "depth-anything/DA3-BASE",
}
SCALE_FACTOR = 300.0


def focal_for_processed(f_orig_px: float, orig_wh: tuple[int, int], proc_wh: tuple[int, int]) -> float:
    """元の画像の px の焦点距離を、DA3 が見た（縮めた）画像の px に直す（fx は幅の比、fy は高さの比の平均）"""
    (w, h), (wp, hp) = orig_wh, proc_wh
    return (f_orig_px * wp / w + f_orig_px * hp / h) / 2


def focal_to_original(intrinsics_proc: np.ndarray, orig_wh: tuple[int, int], proc_wh: tuple[int, int]) -> float:
    """縮めた画像のカメラの情報（px）から、元の画像の px の焦点距離（fx・fy の平均）を出す"""
    (w, h), (wp, hp) = orig_wh, proc_wh
    return float((intrinsics_proc[0, 0] * w / wp + intrinsics_proc[1, 1] * h / hp) / 2)


def metric_depth_mm(canonical: np.ndarray, f_proc_px: float) -> np.ndarray:
    """出力（標準の深度）を、実際の深度（mm）にする：出力 × 焦点距離 ÷ 300（m）× 1000"""
    return canonical * (f_proc_px / SCALE_FACTOR) * 1000.0


@dataclass
class MetricResult:
    depth_mm: np.ndarray       # 元の画像の大きさ
    f_px: float                # 使った焦点距離（元の画像の px）
    proc_wh: tuple[int, int]   # DA3 が見た画像の大きさ
    infer_s: float


class DA3Backend:
    def __init__(self, kind: str):
        if kind not in MODELS:  # ライブラリを読み込む前に止める
            raise SystemExit(f"使えないモデルです：{kind}（metric か base。非営利の版は使わない）")
        import torch
        from depth_anything_3.api import DepthAnything3

        self.torch = torch
        self.kind = kind
        self.repo = MODELS[kind]
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        CHECKPOINTS.mkdir(parents=True, exist_ok=True)
        self.model = DepthAnything3.from_pretrained(self.repo, cache_dir=str(CHECKPOINTS)).to(self.device).eval()

    def _run(self, rgb: np.ndarray, process_res: int = 504):
        torch = self.torch
        if self.device.type == "cuda":
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        with torch.no_grad():
            pred = self.model.inference([rgb], process_res=process_res)  # 既定は 504px（長い辺）
        if self.device.type == "cuda":
            torch.cuda.synchronize()
        return pred, time.perf_counter() - t0

    def metric(self, rgb: np.ndarray, f_orig_px: float, process_res: int = 504) -> MetricResult:
        """DA3METRIC：焦点距離（元の画像の px）を与えて、実際の深度（mm、元の画像の大きさ）を返す。
        process_res：DA3 が見る画像の長い辺（既定 504px。大きくすると細かく見る）"""
        if self.kind != "metric":
            raise RuntimeError("metric() は DA3METRIC-LARGE でだけ使う")
        h, w = rgb.shape[:2]
        pred, dt = self._run(rgb, process_res)
        canonical = np.asarray(pred.depth[0], dtype=np.float32)
        hp, wp = canonical.shape
        f_p = focal_for_processed(f_orig_px, (w, h), (wp, hp))
        depth = metric_depth_mm(canonical, f_p)
        depth = cv2.resize(depth, (w, h), interpolation=cv2.INTER_LINEAR)
        return MetricResult(depth.astype(np.float32), float(f_orig_px), (wp, hp), dt)

    def focal(self, rgb: np.ndarray) -> tuple[float, float]:
        """DA3-BASE：カメラの情報から、元の画像の px の焦点距離を返す（焦点距離、秒）"""
        if self.kind != "base":
            raise RuntimeError("focal() は DA3-BASE でだけ使う")
        h, w = rgb.shape[:2]
        pred, dt = self._run(rgb)
        if pred.intrinsics is None:
            raise SystemExit("DA3-BASE がカメラの情報を返しませんでした")
        hp, wp = np.asarray(pred.depth[0]).shape
        return focal_to_original(np.asarray(pred.intrinsics[0]), (w, h), (wp, hp)), dt

    def device_name(self) -> str:
        return self.torch.cuda.get_device_name(0) if self.device.type == "cuda" else "cpu"


class ConstantBackend:
    """動作確認用の偽物。DA3 と同じく長い辺 504px・14px の倍数に縮めた大きさで「標準の深度」を返し、
    どの焦点距離を与えても実際の深度が 300mm になるようにする。結果を実験に使ってはいけない"""

    kind = "metric"
    repo = "constant"

    @staticmethod
    def proc_size(w: int, h: int) -> tuple[int, int]:
        s = 504 / max(w, h)
        r = lambda x: max(14, int(round(x / 14)) * 14)  # noqa: E731
        return r(w * s), r(h * s)

    def metric(self, rgb: np.ndarray, f_orig_px: float) -> MetricResult:
        h, w = rgb.shape[:2]
        wp, hp = self.proc_size(w, h)
        f_p = focal_for_processed(f_orig_px, (w, h), (wp, hp))
        canonical = np.full((hp, wp), 0.3 * SCALE_FACTOR / f_p, np.float32)  # 0.3m になる出力
        depth = cv2.resize(metric_depth_mm(canonical, f_p), (w, h), interpolation=cv2.INTER_LINEAR)
        return MetricResult(depth.astype(np.float32), float(f_orig_px), (wp, hp), 0.0)

    def focal(self, rgb: np.ndarray) -> tuple[float, float]:
        h, w = rgb.shape[:2]
        return dp.f_px_from_35mm(26.0, w, h), 0.0

    def device_name(self) -> str:
        return "cpu"
