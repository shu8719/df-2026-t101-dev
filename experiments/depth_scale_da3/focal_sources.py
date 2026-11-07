"""焦点距離の出どころ（docs/depth-scale-da3/scripts.md §4）。

写真1枚では、Depth Pro・MoGe-2 の try_image が保存した JSON を読む。どれも元の画像（JSON に書かれた width・height）の px。
DA3 に渡す画像の大きさが違えば、その比で直して返す。
"""
from __future__ import annotations

import math
from pathlib import Path

from da3_backend import dp

REPO_EXP = Path(__file__).resolve().parent.parent  # experiments/
SOURCES = ("depthpro", "moge2vits", "moge2vitl", "da3base")


def image_json(source: str, stem: str) -> Path:
    if source == "depthpro":
        return REPO_EXP / "depth_scale" / "data" / "vis" / f"{stem}_depthpro.json"
    if source in ("moge2vits", "moge2vitl"):
        return REPO_EXP / "depth_scale_moge2" / "data" / "vis" / f"{stem}_moge2_{source[-4:]}.json"
    raise ValueError(source)


def how_to_make(source: str) -> str:
    if source == "depthpro":
        return "experiments/depth_scale で .venv\\Scripts\\python try_image.py <写真> を先に動かしてください"
    return f"experiments/depth_scale_moge2 で .venv\\Scripts\\python try_image_moge.py <写真> --model {source[-4:]} を先に動かしてください"


def load_image_result(source: str, stem: str) -> dict:
    """Depth Pro・MoGe-2 の写真1枚の結果（焦点距離・5点の距離・長さ）。なければ作り方を伝えて止める"""
    p = image_json(source, stem)
    if not p.exists():
        raise SystemExit(f"{source} の結果（{p}）がありません。{how_to_make(source)}")
    return dp.load_json(p)


def scale_focal(f_px: float, from_wh: tuple[int, int], to_wh: tuple[int, int]) -> float:
    """画像の大きさが違うときに、焦点距離（px）を直す（幅の比と高さの比の平均）"""
    (w0, h0), (w1, h1) = from_wh, to_wh
    return f_px * (w1 / w0 + h1 / h0) / 2


def image_focal(source: str, stem: str, wh: tuple[int, int]) -> float:
    """写真1枚の焦点距離（DA3 に渡す画像の大きさ wh の px）"""
    r = load_image_result(source, stem)
    f = float(r["f_px"])
    if not math.isfinite(f) or f <= 0:
        raise SystemExit(f"{source} の焦点距離が正しくありません：{f}")
    return scale_focal(f, (int(r["width"]), int(r["height"])), wh)
