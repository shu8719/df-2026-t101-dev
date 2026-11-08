"""焦点距離の出どころ（docs/depth-scale-yolo26/method.md §2、scripts.md §2）。

どれも「長い辺を縮めた、測るときの画像（W×H）」の px で返す。見つからなければ None。
- exif     ：写真の撮影情報の 35mm 換算の焦点距離。切り取る前の大きさ（長い辺 × 3/4 を短い辺）の対角線で計算
- fixed26  ：「スマホの広角は 35mm 換算 26mm」と決め打ち（同じ式）。本番で使える
- depthpro ：Depth Pro の推定（研究目的の物差しとしてだけ）
- moge2    ：MoGe-2（vitl）の推定
"""
from __future__ import annotations

import math
from pathlib import Path

from yolo26_backend import EXP, dp

SOURCES = ("exif", "fixed26", "depthpro", "moge2")
SENSOR_ASPECT = 3 / 4  # iPhone の広角の撮像素子は 4:3
DIAG_35MM = 43.27


def f_px_from_35mm_uncropped(f35: float, long_side_px: int, work_long_side: int) -> float:
    """35mm 換算の焦点距離から、測るときの画像の px の焦点距離を出す。
    画像は撮像素子（4:3）の長い辺を保ったまま、短い辺の側を切り取ってあることがある（9:16 など）ので、
    切り取る前の対角線（長い辺 × √(1 + (3/4)²)）で計算し、縮めた割合を掛ける"""
    diag = long_side_px * math.sqrt(1 + SENSOR_ASPECT ** 2)
    return f35 * diag / DIAG_35MM * (work_long_side / long_side_px)


def exif_info(path: Path) -> tuple[float | None, int]:
    """撮影情報の 35mm 換算の焦点距離（なければ None）と、元の画像の長い辺（px）"""
    from PIL import Image, ExifTags

    im = Image.open(path)
    ex = im.getexif()
    tags = {ExifTags.TAGS.get(k, k): v for k, v in list(ex.items()) + list(ex.get_ifd(0x8769).items())}
    f35 = tags.get("FocalLengthIn35mmFilm")
    return (float(f35) if f35 else None), max(im.size)


def _from_json(p: Path, wh: tuple[int, int]) -> float | None:
    if not p.exists():
        return None
    r = dp.load_json(p)
    w0, h0 = int(r["width"]), int(r["height"])
    return float(r["f_px"]) * (wh[0] / w0 + wh[1] / h0) / 2


def focal(source: str, image: Path, wh: tuple[int, int]) -> float | None:
    """測るときの画像（大きさ wh）の px の焦点距離"""
    work_long = max(wh)
    if source in ("exif", "fixed26"):
        f35, long0 = exif_info(image)
        if source == "fixed26":
            f35 = 26.0
        return f_px_from_35mm_uncropped(f35, long0, work_long) if f35 else None
    if source == "depthpro":
        return _from_json(EXP / "depth_scale" / "data" / "vis" / f"{image.stem}_depthpro.json", wh)
    if source == "moge2":
        return _from_json(EXP / "depth_scale_moge2" / "data" / "vis" / f"{image.stem}_moge2_vitl.json", wh)
    raise ValueError(source)
