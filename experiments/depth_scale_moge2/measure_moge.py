"""④ 手の甲の4区間の長さ（docs/depth-scale-moge2/scripts.md §5.1）。

本命（source=points）：点のまわりの点群の x・y・z それぞれの中央値を3D位置にして長さを出す。
確かめ（source=depth）：深度と焦点距離から、Depth Pro と同じ式で3Dに直して長さを出す。
集計（上位20%・最低3枚の中央値）と8枚の選び方は、Depth Pro 側と同じ関数を使う。

使い方：python measure_moge.py --all --model vitl,vits --cond A,B,C --radius 1,3,5 --skin-offset-mm 0,10
"""
from __future__ import annotations

import argparse
import sys

import numpy as np

import moge_backend as mb
from moge_backend import dp
import measure as dp_measure  # Depth Pro 側の集計（aggregate）を使う

FIELDS = ["rec_id", "model", "cond", "source", "radius_px", "skin_offset_mm", "subset", *dp.SEGMENTS,
          "frames_used", "iqr_ratio_max", "f_px_median", "status"]
LENGTH_POINTS = dp_measure.LENGTH_POINTS


def lengths_from_points(npz, key_of, radius: float, offset: float) -> dict[str, float] | None:
    xyz = {}
    for p in LENGTH_POINTS:
        q = mb.patch_point(npz[f"{key_of(p)}_points"], npz[f"{key_of(p)}_mask"], radius)
        if q is None:
            return None
        xyz[p] = mb.push_out(q, offset)
    return {k: float(np.linalg.norm(xyz[a] - xyz[b])) for k, (a, b) in dp.SEGMENTS.items()}


def lengths_from_depth(npz, key_of, points_px, f_px, cx, cy, radius: float, offset: float) -> dict[str, float] | None:
    xyz = {}
    for p in LENGTH_POINTS:
        d = npz[f"{key_of(p)}_depth"].copy()
        d[np.nan_to_num(npz[f"{key_of(p)}_mask"], nan=0.0) <= 0.5] = np.nan
        z = dp.patch_depth(d, radius)
        if z is None:
            return None
        xyz[p] = dp.backproject(*points_px[p], z + offset, f_px, cx, cy)
    return {k: float(np.linalg.norm(xyz[a] - xyz[b])) for k, (a, b) in dp.SEGMENTS.items()}


def measure(rec_id: str, model_key: str, cond: str, radii: list[float], offsets: list[float]) -> list[dict]:
    pj = mb.DATA / "points" / rec_id / f"{model_key}_{cond}.json"
    if not pj.exists():
        print(f"{rec_id} {model_key} {cond}: 推定の結果がないので飛ばします（先に depth_moge.py）")
        return []
    meta = dp.load_json(pj)
    npz = np.load(pj.with_suffix(".npz"))
    frames = {f["index"]: f for f in dp.load_json(dp.DATA / "frames" / rec_id / "frames.json")["frames"]}
    lms = {r["index"]: r for r in dp.load_json(dp.DATA / "landmarks" / f"{rec_id}.json")["frames"]}
    drows = sorted(meta["frames"], key=lambda r: r["index"])
    subsets = {"all": drows}
    if cond == "B":
        subsets["8"] = dp.even_subset(drows, 8)

    rows = []
    for subset, chosen in subsets.items():
        for source in ("points", "depth"):
            for r in radii:
                for off in offsets:
                    per_frame, fs = [], []
                    for d in chosen:
                        idx = d["index"]
                        fr = frames[idx]
                        key_of = lambda p, idx=idx: f"f{idx:03d}_p{p}"  # noqa: E731
                        if source == "points":
                            L = lengths_from_points(npz, key_of, r, off)
                        else:
                            L = lengths_from_depth(npz, key_of, lms[idx]["points_px"], d["f_px"],
                                                   fr["width"] / 2, fr["height"] / 2, r, off)
                        if L is not None:
                            per_frame.append(L)
                            fs.append(d["f_px"])
                    row = {"rec_id": rec_id, "model": model_key, "cond": cond, "source": source, "radius_px": r,
                           "skin_offset_mm": off, "subset": subset,
                           "f_px_median": round(dp.median(fs), 2) if fs else ""}
                    row.update(dp_measure.aggregate(per_frame))
                    rows.append(row)
    return rows


def parse_list(s: str) -> list[float]:
    return [float(x) for x in s.split(",") if x.strip()]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rec")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--model", default="vitl,vits")
    ap.add_argument("--cond", default="A,B,C")
    ap.add_argument("--radius", default="3")
    ap.add_argument("--skin-offset-mm", default="0")
    a = ap.parse_args(argv)
    ids = dp.rec_ids(a.rec, a.all)
    models = [m.strip() for m in a.model.split(",")]
    conds = [c.strip().upper() for c in a.cond.split(",")]
    out = mb.DATA / "results" / "lengths.csv"
    old = dp.read_csv(out) if out.exists() else []
    keep = [r for r in old if not (r["rec_id"] in ids and r["model"] in models and r["cond"] in conds)]
    new = []
    for rid in ids:
        for m in models:
            for c in conds:
                new += measure(rid, m, c, parse_list(a.radius), parse_list(a.skin_offset_mm))
    dp.write_csv(out, keep + new, FIELDS)
    print(f"{out} に {len(new)} 行を書きました")


if __name__ == "__main__":
    sys.exit(main())
