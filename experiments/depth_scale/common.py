"""実験スクリプトの共通の関数（docs/depth-scale/scripts.md）。

3Dに直す式、焦点距離の換算、点のまわりの深度、集計、ずれの計算、ファイルの読み書きをまとめる。
本番の計算（app/web_engine/src/geometry.ts の topMedian・iqr）と同じ定義にする。
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
REPO = HERE.parent.parent

# 手の甲の4区間（docs/measurement.md §8.2）。列名 → MediaPipe の点の番号
SEGMENTS: dict[str, tuple[int, int]] = {
    "seg_0_5_mm": (0, 5),
    "seg_0_9_mm": (0, 9),
    "seg_0_17_mm": (0, 17),
    "seg_5_17_mm": (5, 17),
}
# 深度を保存する点（手首と指の付け根。scripts.md §5.1）
DEPTH_POINTS: tuple[int, ...] = (0, 5, 9, 13, 17)
PATCH = 31  # 点のまわりの深度を保存する大きさ（px、奇数）
CROP_LONG_SIDE = 512  # 本番で hand-mesh に送る切り抜きの長い辺（px）
DIAG_35MM = 43.27  # 36×24mm の対角線（mm）


# ---------- 幾何 ----------

def backproject(u: float, v: float, z_mm: float, f_px: float, cx: float, cy: float) -> np.ndarray:
    """画像の上の位置（px）と深度（mm）から、カメラから見た3Dの位置（mm）を出す（method.md §1.1）"""
    return np.array([(u - cx) * z_mm / f_px, (v - cy) * z_mm / f_px, z_mm], dtype=float)


def f_px_from_35mm(focal_35mm_mm: float, width: int, height: int) -> float:
    """35mm換算の焦点距離から、その画像の px の焦点距離を出す（scripts.md §5.3）"""
    return focal_35mm_mm * math.hypot(width, height) / DIAG_35MM


def f_crop_to_orig(f_crop_px: float, crop_long_side_px: float, out_long_side: int = CROP_LONG_SIDE) -> float:
    """切り抜いて縮めた画像の焦点距離を、元のフレームの px に戻す（scripts.md §5.4）"""
    s = out_long_side / crop_long_side_px
    return f_crop_px / s


def crop_box(points_px: Iterable[Iterable[float]], width: int, height: int, expand: float = 0.2) -> tuple[float, float, float, float]:
    """21点を囲む四角を、幅・高さの20%ずつ広げた範囲（app/web_engine/src/engine.ts の cropHand と同じ）"""
    pts = np.asarray(list(points_px), dtype=float)
    x0, y0 = pts.min(axis=0)
    x1, y1 = pts.max(axis=0)
    mx, my = (x1 - x0) * expand, (y1 - y0) * expand
    return (max(0.0, x0 - mx), max(0.0, y0 - my), min(float(width), x1 + mx), min(float(height), y1 + my))


def extract_patch(depth: np.ndarray, u: float, v: float, size: int = PATCH) -> np.ndarray:
    """深度マップから、点を中心に size×size を切り出す。画像の外は NaN で埋める"""
    h, w = depth.shape
    r = size // 2
    cu, cv = int(round(u)), int(round(v))
    out = np.full((size, size), np.nan, dtype=np.float32)
    x0, x1 = max(0, cu - r), min(w, cu + r + 1)
    y0, y1 = max(0, cv - r), min(h, cv + r + 1)
    if x0 < x1 and y0 < y1:
        out[y0 - (cv - r):y1 - (cv - r), x0 - (cu - r):x1 - (cu - r)] = depth[y0:y1, x0:x1]
    return out


def patch_depth(patch: np.ndarray, radius: float) -> float | None:
    """切り出した深度のうち、中心から半径 radius px の円の中の、有効な値（有限で0より大きい）の中央値"""
    size = patch.shape[0]
    c = size // 2
    yy, xx = np.mgrid[0:size, 0:size]
    inside = (xx - c) ** 2 + (yy - c) ** 2 <= radius ** 2
    vals = patch[inside]
    vals = vals[np.isfinite(vals) & (vals > 0)]
    if vals.size == 0:
        return None
    return float(np.median(vals))


# ---------- 集計 ----------

def median(xs: Iterable[float]) -> float:
    s = sorted(x for x in xs if math.isfinite(x))
    if not s:
        return math.nan
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def quantile(xs: Iterable[float], q: float) -> float:
    s = sorted(x for x in xs if math.isfinite(x))
    if not s:
        return math.nan
    pos = (len(s) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def iqr(xs: Iterable[float]) -> float:
    xs = list(xs)
    return quantile(xs, 0.75) - quantile(xs, 0.25)


def top_median(xs: Iterable[float], frac: float = 0.2, min_n: int = 3) -> float:
    """長く写ったフレームの上位20%（最低3枚）の中央値（measurement.md §7.1、geometry.ts の topMedian）"""
    s = sorted((x for x in xs if math.isfinite(x)), reverse=True)
    if not s:
        return math.nan
    k = min(len(s), max(min_n, math.ceil(len(s) * frac)))
    return median(s[:k])


def even_subset(items: list, n: int = 8) -> list:
    """時間の順に並んだものから、等しい間隔で n 個を選ぶ（scripts.md §6.3）"""
    if len(items) <= n:
        return list(items)
    idx = sorted({int(round(i)) for i in np.linspace(0, len(items) - 1, n)})
    return [items[i] for i in idx]


# ---------- ずれ ----------

def scale_ratio(lengths: dict[str, float], truth: dict[str, float]) -> float:
    """4区間の「長さ ÷ ノギスの長さ」の中央値（experiment.md §4）"""
    return median(lengths[k] / truth[k] for k in SEGMENTS if math.isfinite(lengths.get(k, math.nan)) and truth.get(k))


def deviation_pct(ratio: float) -> float:
    return (ratio - 1.0) * 100.0


def loo_corrected(ratios: dict[str, list[float]]) -> dict[str, list[float]]:
    """1人を除いた全員の比の平均から補正係数を出し、除いた1人に掛けたあとの比（scripts.md §7.2）。

    ratios：人 → その人の撮影ごとの比。ほかに人がいなければ NaN。
    """
    out: dict[str, list[float]] = {}
    for p, rs in ratios.items():
        others = [r for q, xs in ratios.items() if q != p for r in xs if math.isfinite(r)]
        if not others:
            out[p] = [math.nan for _ in rs]
            continue
        c = 1.0 / (sum(others) / len(others))
        out[p] = [r * c for r in rs]
    return out


# ---------- ファイル ----------

def load_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(path: Path, obj) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def recordings(data: Path | None = None) -> list[dict[str, str]]:
    # 既定値を DATA にすると、関数を作った時点の場所に固定される。呼ばれたときに決める
    return read_csv((data or DATA) / "recordings.csv")


def rec_ids(args_rec: str | None, args_all: bool, data: Path | None = None) -> list[str]:
    """--rec か --all から、処理する撮影IDの一覧を作る"""
    if args_rec:
        return [args_rec]
    if args_all:
        return [r["rec_id"] for r in recordings(data)]
    raise SystemExit("--rec <撮影ID> か --all を指定してください")


def to_float(s: str | None) -> float:
    try:
        return float(s) if s not in (None, "") else math.nan
    except ValueError:
        return math.nan
