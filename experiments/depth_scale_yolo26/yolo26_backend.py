"""YOLO26 Depth の読み込みと推論（docs/depth-scale-yolo26/method.md §1）。

r = YOLO("yolo26x-depth.pt")(画像, imgsz=768)[0]; r.depth.data は (H, W) のメートル（公式のドキュメント）。
距離を mm にし、元の画像の大きさにそろえて返す。焦点距離は出さない（focal.py で別に決める）。
ライセンス：ultralytics は AGPL-3.0（配布物の表示）。重みのライセンスは要確認。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
if str(EXP / "depth_scale") not in sys.path:
    sys.path.insert(0, str(EXP / "depth_scale"))

import common as dp  # noqa: E402

DATA = HERE / "data"
CHECKPOINTS = HERE / "checkpoints"
SIZES = ("n", "s", "m", "l", "x")
IMGSZ = 768  # 公式の推奨（学習と同じ大きさ）


class Yolo26Depth:
    def __init__(self, size: str):
        if size not in SIZES:
            raise SystemExit(f"知らない大きさです：{size}（n・s・m・l・x）")
        from ultralytics import YOLO

        CHECKPOINTS.mkdir(parents=True, exist_ok=True)
        self.size = size
        self.model = YOLO(str(CHECKPOINTS / f"yolo26{size}-depth.pt"))  # なければ公式の配布元から取ってくる

    def depth_mm(self, bgr: np.ndarray, imgsz: int = IMGSZ) -> tuple[np.ndarray, float]:
        """BGR の画像から、距離（mm、元の画像と同じ大きさ）と推論の秒数を返す。imgsz：モデルが見る大きさ（既定 768）"""
        h, w = bgr.shape[:2]
        t0 = time.perf_counter()
        r = self.model(bgr, imgsz=imgsz, verbose=False)[0]
        dt = time.perf_counter() - t0
        d = r.depth.data
        d = (d.detach().float().cpu().numpy() if hasattr(d, "detach") else np.asarray(d, np.float32)).squeeze()
        if d.shape != (h, w):
            d = cv2.resize(d, (w, h), interpolation=cv2.INTER_LINEAR)
        return (d * 1000.0).astype(np.float32), dt


class ConstantDepth:
    """動作確認用の偽物：どこも 300mm。結果を実験に使ってはいけない"""

    size = "constant"

    def depth_mm(self, bgr: np.ndarray) -> tuple[np.ndarray, float]:
        return np.full(bgr.shape[:2], 300.0, np.float32), 0.0
