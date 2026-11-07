"""④ 3Dに直して、手の甲の4区間の長さを出す（docs/depth-scale/scripts.md §6）。

フレームごとに、点のまわりの深度の中央値 Z と焦点距離 f から3Dの位置にし、4区間の長さを出す。
撮影ごとに、上位20%（最低3枚）の中央値で集計する（docs/measurement.md §7.1）。

使い方：python measure.py --all --cond A,B,C --radius 1,3,5 --skin-offset-mm 0,10
"""
from __future__ import annotations

import argparse
import math
import sys

import numpy as np

import common

FIELDS = ["rec_id", "cond", "radius_px", "skin_offset_mm", "subset", *common.SEGMENTS,
          "frames_used", "iqr_ratio_max", "f_px_median", "status"]
LENGTH_POINTS = sorted({p for seg in common.SEGMENTS.values() for p in seg})


def frame_lengths(points_px: list, patches: dict[int, np.ndarray], f_px: float, cx: float, cy: float,
                  radius: float, skin_offset_mm: float) -> dict[str, float] | None:
    """1枚のフレームの4区間の長さ（mm）。どれかの点の深度が出なければ None"""
    xyz = {}
    for p in LENGTH_POINTS:
        z = common.patch_depth(patches[p], radius)
        if z is None:
            return None
        u, v = points_px[p]
        xyz[p] = common.backproject(u, v, z + skin_offset_mm, f_px, cx, cy)
    return {k: float(np.linalg.norm(xyz[a] - xyz[b])) for k, (a, b) in common.SEGMENTS.items()}


def aggregate(per_frame: list[dict[str, float]]) -> dict:
    if len(per_frame) < 3:
        return {"frames_used": len(per_frame), "status": "FEW_FRAMES"}
    out: dict = {"frames_used": len(per_frame), "status": "ok"}
    ratios = []
    for k in common.SEGMENTS:
        xs = [f[k] for f in per_frame]
        L = common.top_median(xs)
        out[k] = round(L, 2)
        ratios.append(common.iqr(xs) / L if L > 0 else math.nan)
    out["iqr_ratio_max"] = round(max(ratios), 4)
    return out


def measure(rec_id: str, cond: str, radii: list[float], offsets: list[float]) -> list[dict]:
    dj = common.DATA / "depth" / rec_id / f"{cond}.json"
    if not dj.exists():
        print(f"{rec_id} {cond}: 深度がないので飛ばします（先に depth.py）")
        return []
    dmeta = common.load_json(dj)
    npz = np.load(dj.with_suffix(".npz"))
    frames = {f["index"]: f for f in common.load_json(common.DATA / "frames" / rec_id / "frames.json")["frames"]}
    lms = {r["index"]: r for r in common.load_json(common.DATA / "landmarks" / f"{rec_id}.json")["frames"]}

    drows = sorted(dmeta["frames"], key=lambda r: r["index"])
    subsets = {"all": drows}
    if cond == "B":
        subsets["8"] = common.even_subset(drows, 8)  # 本番で hand-mesh に送るのは最大8枚

    rows = []
    for subset, chosen in subsets.items():
        for r in radii:
            for off in offsets:
                per_frame, fs = [], []
                for d in chosen:
                    idx = d["index"]
                    fr = frames[idx]
                    patches = {p: npz[f"f{idx:03d}_p{p}"] for p in LENGTH_POINTS}
                    L = frame_lengths(lms[idx]["points_px"], patches, d["f_px"], fr["width"] / 2, fr["height"] / 2, r, off)
                    if L is not None:
                        per_frame.append(L)
                        fs.append(d["f_px"])
                row = {"rec_id": rec_id, "cond": cond, "radius_px": r, "skin_offset_mm": off, "subset": subset,
                       "f_px_median": round(common.median(fs), 2) if fs else ""}
                row.update(aggregate(per_frame))
                rows.append(row)
    return rows


def parse_list(s: str) -> list[float]:
    return [float(x) for x in s.split(",") if x.strip()]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rec")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--cond", default="A,B,C")
    ap.add_argument("--radius", default="3", help="点のまわりの深度を取る半径（px）。カンマ区切りで複数")
    ap.add_argument("--skin-offset-mm", default="0", help="深度に足す量（皮膚と関節の中心のずれ）。カンマ区切りで複数")
    a = ap.parse_args(argv)
    ids = common.rec_ids(a.rec, a.all)
    conds = [c.strip().upper() for c in a.cond.split(",")]
    out = common.DATA / "results" / "lengths.csv"
    old = common.read_csv(out) if out.exists() else []
    keep = [r for r in old if not (r["rec_id"] in ids and r["cond"] in conds)]
    new = []
    for rid in ids:
        for c in conds:
            new += measure(rid, c, parse_list(a.radius), parse_list(a.skin_offset_mm))
    common.write_csv(out, keep + new, FIELDS)
    print(f"{out} に {len(new)} 行を書きました")


if __name__ == "__main__":
    sys.exit(main())
