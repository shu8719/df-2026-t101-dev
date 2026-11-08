"""MapAnything の読み込み・前処理・推論（docs/depth-scale-mapanything/scripts.md §2）。

コードを読んで確かめたこと（MapAnything、コミット 3d10cf7、2026-11-08）：
- preprocess_inputs([{"img": PIL の画像}]) でメモリの中の画像を渡せる。既定の fixed_mapping では、
  縦横の比を決まった組み合わせ（解像度の組 518）に合わせ、縮めたうえで切り取る（crop_resize_if_necessary）
- model.infer の出力：pts3d_cam（カメラから見た3D位置）、depth_z、intrinsics、conf、mask、metric_scaling_factor、
  img_no_norm（モデルが見た画像）。単位はメートルと見込む
- 切り取りがあるので、MediaPipe はモデルが見た画像（img_no_norm）にかける（点と3D位置が同じ画素の並びになる）
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
for d in (EXP / "depth_scale", EXP / "depth_scale_moge2"):  # Depth Pro・MoGe-2 の実験の関数（読むだけ）
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

import common as dp  # noqa: E402

DATA = HERE / "data"
CHECKPOINTS = HERE / "checkpoints"
REPO = "facebook/map-anything-apache"          # Apache-2.0。これだけを使う
NON_COMMERCIAL = {"facebook/map-anything"}     # CC BY-NC 4.0。読み込まない


@dataclass
class Result:
    rgb: np.ndarray        # モデルが見た画像（H, W, 3）uint8
    points_mm: np.ndarray  # (H, W, 3)。使えない画素は NaN
    depth_mm: np.ndarray   # (H, W)
    conf: np.ndarray       # (H, W)
    mask: np.ndarray       # (H, W) bool
    f_px: float            # モデルが見た画像の px の焦点距離（fx・fy の平均）
    scale: float           # metric_scaling_factor
    infer_s: float


def check_repo(repo: str) -> str:
    if repo in NON_COMMERCIAL or repo != REPO:
        raise SystemExit(f"使えない重みです：{repo}（{REPO} だけを使う。非営利の版は使わない）")
    return repo


def focal_to_original(f_model: float, orig_wh: tuple[int, int], model_wh: tuple[int, int]) -> float:
    """モデルが見た画像の焦点距離を、元の画像の px に直す。
    縮めてから切り取る（覆うように縮めて、はみ出した分を切る）と見込み、縮めた割合 = max(幅の比, 高さの比)（要確認）"""
    (w, h), (wm, hm) = orig_wh, model_wh
    return f_model / max(wm / w, hm / h)


def _np(x) -> np.ndarray:
    return x.detach().float().cpu().numpy() if hasattr(x, "detach") else np.asarray(x)


class MapAnythingBackend:
    def __init__(self, repo: str = REPO):
        check_repo(repo)  # ライブラリを読み込む前に止める
        os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
        import torch
        from mapanything.models import MapAnything

        self.torch = torch
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        CHECKPOINTS.mkdir(parents=True, exist_ok=True)
        self.model = MapAnything.from_pretrained(repo, cache_dir=str(CHECKPOINTS)).to(self.device).eval()
        self.repo = repo

    def infer(self, rgb: np.ndarray) -> Result:
        import PIL.Image
        from mapanything.utils.image import preprocess_inputs

        torch = self.torch
        views = preprocess_inputs([{"img": PIL.Image.fromarray(rgb)}])
        if self.device.type == "cuda":
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        with torch.no_grad():
            pred = self.model.infer(views, memory_efficient_inference=True, use_amp=True, amp_dtype="bf16",
                                    apply_mask=True, mask_edges=True, apply_confidence_mask=False)[0]
        if self.device.type == "cuda":
            torch.cuda.synchronize()
        dt = time.perf_counter() - t0
        img = _np(pred["img_no_norm"])[0]
        img = (img * 255 if img.max() <= 1.0 + 1e-6 else img).clip(0, 255).astype(np.uint8)
        pts = _np(pred["pts3d_cam"])[0] * 1000.0
        depth = _np(pred["depth_z"])[0][..., 0] * 1000.0
        conf = _np(pred["conf"])[0]
        mask = _np(pred["mask"])[0][..., 0] > 0.5
        pts[~mask] = np.nan
        K = _np(pred["intrinsics"])[0]
        scale = float(_np(pred["metric_scaling_factor"]).reshape(-1)[0])
        return Result(img, pts.astype(np.float32), depth.astype(np.float32), conf.astype(np.float32), mask,
                      float((K[0, 0] + K[1, 1]) / 2), scale, dt)

    def device_name(self) -> str:
        return self.torch.cuda.get_device_name(0) if self.device.type == "cuda" else "cpu"


class ConstantBackend:
    """動作確認用の偽物。入力をそのまま「モデルが見た画像」として返し、カメラから300mmの平らな面の点群を返す
    （焦点距離は35mm換算26mm相当、画素の中心 i+0.5 で作る）。結果を実験に使ってはいけない"""

    repo = "constant"

    def infer(self, rgb: np.ndarray) -> Result:
        h, w = rgb.shape[:2]
        f = dp.f_px_from_35mm(26.0, w, h)
        u, v = np.meshgrid(np.arange(w, dtype=np.float32) + 0.5, np.arange(h, dtype=np.float32) + 0.5)
        z = np.full_like(u, 300.0)
        pts = np.stack([(u - w / 2) * z / f, (v - h / 2) * z / f, z], axis=-1)
        return Result(rgb.copy(), pts, z, np.ones_like(z), np.ones((h, w), bool), float(f), 1.0, 0.0)

    def device_name(self) -> str:
        return "cpu"
