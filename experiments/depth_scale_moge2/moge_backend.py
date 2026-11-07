"""MoGe-2 の読み込みと推論（docs/depth-scale-moge2/scripts.md §3）。

MoGe-2 の出力（点群・深度はメートル、カメラの情報は正規化）を、mm と px に直して返す。
Depth Pro の実験（experiments/depth_scale/）の common.py を読み込んで、同じ計算を使う。

正規化されたカメラの情報（MoGe の moge/model/v2.py の infer で確かめた、コミット 74fbce0）：
  fx は画像の幅を1、fy は高さを1とした焦点距離、中心は (0.5, 0.5)。
  したがって px の焦点距離は f_px = fx × 幅 = fy × 高さ（2つは同じ値になる）。
  画角を与えるときの式は f_px = 幅 ÷ (2·tan(fov_x ÷ 2))（同じファイルの式から導いた）。
"""
from __future__ import annotations

import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DP_DIR = HERE.parent / "depth_scale"  # Depth Pro の実験のフォルダ（読むだけ）
if str(DP_DIR) not in sys.path:
    sys.path.insert(0, str(DP_DIR))

import common as dp  # noqa: E402  Depth Pro 側の共通の関数（3Dに直す式・集計など）

DATA = HERE / "data"
CHECKPOINTS = HERE / "checkpoints"
REPOS = {"vitl": "Ruicheng/moge-2-vitl-normal", "vits": "Ruicheng/moge-2-vits-normal"}


@dataclass
class Result:
    points_mm: np.ndarray  # (H, W, 3)。使えない画素は inf
    depth_mm: np.ndarray   # (H, W)。使えない画素は inf
    mask: np.ndarray       # (H, W) bool
    f_px: float
    infer_s: float
    normal: np.ndarray | None = None  # (H, W, 3)。面の向き（画像に描くためだけ）


def f_px_from_normalized(intrinsics: np.ndarray, width: int, height: int) -> float:
    """正規化されたカメラの情報から、px の焦点距離（fx・fy の平均）を出す"""
    return float((intrinsics[0, 0] * width + intrinsics[1, 1] * height) / 2)


def fov_x_from_f_px(f_px: float, width: int) -> float:
    """px の焦点距離から、水平の画角（度）を出す（MoGe に与えるため）"""
    return math.degrees(2 * math.atan(width / (2 * f_px)))


class MoGeBackend:
    def __init__(self, model: str):
        import torch
        from moge.model.v2 import MoGeModel

        if model not in REPOS:
            raise SystemExit(f"知らないモデルです：{model}（vitl か vits）")
        self.torch = torch
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        CHECKPOINTS.mkdir(parents=True, exist_ok=True)
        self.model = MoGeModel.from_pretrained(REPOS[model], cache_dir=str(CHECKPOINTS)).to(self.device).eval()
        self.name = f"moge2_{model}"
        self.version = REPOS[model]

    def infer(self, rgb: np.ndarray, fov_x: float | None = None) -> Result:
        torch = self.torch
        h, w = rgb.shape[:2]
        x = torch.from_numpy(rgb).to(self.device).permute(2, 0, 1).float() / 255.0
        if self.device.type == "cuda":
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        with torch.no_grad():
            out = self.model.infer(x, fov_x=fov_x)
        if self.device.type == "cuda":
            torch.cuda.synchronize()
        dt = time.perf_counter() - t0
        points = out["points"].float().cpu().numpy() * 1000.0  # m → mm（単位はメートルと見込む）
        depth = out["depth"].float().cpu().numpy() * 1000.0
        mask = out["mask"].cpu().numpy().astype(bool) if "mask" in out else np.isfinite(depth)
        f_px = f_px_from_normalized(out["intrinsics"].float().cpu().numpy(), w, h)
        normal = out["normal"].float().cpu().numpy() if "normal" in out else None
        return Result(points.astype(np.float32), depth.astype(np.float32), mask, f_px, dt, normal)

    def device_name(self) -> str:
        return self.torch.cuda.get_device_name(0) if self.device.type == "cuda" else "cpu"


class ConstantBackend:
    """動作確認用の偽物。カメラから300mmの平らな面（焦点距離は35mm換算26mm相当、画角を与えればそれを使う）。
    点群は MoGe と同じく画素の中心（i + 0.5）で作る。結果を実験に使ってはいけない"""

    name = "constant"
    version = "constant-300mm"

    def infer(self, rgb: np.ndarray, fov_x: float | None = None) -> Result:
        h, w = rgb.shape[:2]
        f = w / (2 * math.tan(math.radians(fov_x) / 2)) if fov_x else dp.f_px_from_35mm(26.0, w, h)
        z = 300.0
        u = np.arange(w, dtype=np.float32) + 0.5
        v = np.arange(h, dtype=np.float32) + 0.5
        uu, vv = np.meshgrid(u, v)
        points = np.stack([(uu - w / 2) * z / f, (vv - h / 2) * z / f, np.full_like(uu, z)], axis=-1)
        return Result(points.astype(np.float32), np.full((h, w), z, np.float32), np.ones((h, w), bool), float(f), 0.0)

    def device_name(self) -> str:
        return "cpu"


def make_backend(name: str):
    if name == "constant":
        return ConstantBackend()
    return MoGeBackend(name)


# ---------- 画像に描く（Depth Pro 側の try_image.py の描き方に、MoGe-2 だけの出力を足す） ----------

def draw_mask(bgr: np.ndarray, mask: np.ndarray, pts: list) -> np.ndarray:
    """使える画素（MoGe-2 の mask）は元の写真のまま、使えない画素を赤く塗る"""
    img = bgr.copy()
    bad = ~mask
    img[bad] = (0.4 * img[bad] + 0.6 * np.array([0, 0, 255])).astype(np.uint8)
    for p in dp.DEPTH_POINTS:
        cv2_circle(img, pts[p])
    return img


def draw_normal(normal: np.ndarray | None, shape: tuple[int, int], pts: list) -> np.ndarray:
    """面の向き（法線）を色で表す（x→赤、y→緑、z→青）。法線がなければ灰色"""
    if normal is None:
        return np.full((*shape, 3), 128, np.uint8)
    n = np.nan_to_num(normal, nan=0.0, posinf=0.0, neginf=0.0)
    img = ((n * 0.5 + 0.5).clip(0, 1) * 255).astype(np.uint8)[..., ::-1].copy()  # RGB → BGR
    for p in dp.DEPTH_POINTS:
        cv2_circle(img, pts[p])
    return img


def cv2_circle(img: np.ndarray, pt) -> None:
    import cv2

    x, y = (round(v) for v in pt)
    cv2.circle(img, (x, y), 6, (255, 255, 255), 2, cv2.LINE_AA)


# ---------- 点のまわりの値 ----------

def extract_patch3(arr: np.ndarray, u: float, v: float, size: int = dp.PATCH) -> np.ndarray:
    """(H, W, C) の配列から、点を中心に size×size×C を切り出す。画像の外は NaN"""
    return np.stack([dp.extract_patch(arr[..., c], u, v, size) for c in range(arr.shape[2])], axis=-1)


def patch_point(patch_points: np.ndarray, patch_mask: np.ndarray | None, radius: float) -> np.ndarray | None:
    """切り出した点群のうち、中心から半径 radius px の円の中で、使える（mask があり有限な）画素の x・y・z それぞれの中央値"""
    size = patch_points.shape[0]
    c = size // 2
    yy, xx = np.mgrid[0:size, 0:size]
    inside = (xx - c) ** 2 + (yy - c) ** 2 <= radius ** 2
    ok = inside & np.all(np.isfinite(patch_points), axis=-1)
    if patch_mask is not None:
        ok &= np.nan_to_num(patch_mask, nan=0.0) > 0.5
    vals = patch_points[ok]
    if vals.shape[0] == 0:
        return None
    return np.median(vals, axis=0)


def push_out(p: np.ndarray, offset_mm: float) -> np.ndarray:
    """カメラから点への向きに沿って offset_mm だけ遠ざける（皮膚と関節の中心のずれを試すため）"""
    if offset_mm == 0:
        return p
    n = float(np.linalg.norm(p))
    return p * (n + offset_mm) / n
