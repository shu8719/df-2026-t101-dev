"""③ フレーム → 点のまわりの点群・深度・印（docs/depth-scale-moge2/scripts.md §4）。

フレームと手の21点は、Depth Pro の実験（experiments/depth_scale/data/）の出力を読むだけ。
条件の作り方（A：そのまま、B：本番と同じ切り抜き、C：機種の画角を与える）は Depth Pro 側の depth.py と同じ。

使い方：python depth_moge.py --all --model vitl --cond A,B,C
        --model constant は、重みなしで流れだけを確かめるための偽物
"""
from __future__ import annotations

import argparse
import math
import sys

import cv2
import numpy as np

import moge_backend as mb
from moge_backend import dp


def resize_to(arr: np.ndarray, w: int, h: int) -> np.ndarray:
    if arr.shape[:2] == (h, w):
        return arr
    return cv2.resize(arr, (w, h), interpolation=cv2.INTER_LINEAR)


def save_frame_vis(rec_id: str, model_key: str, cond: str, idx: int, bgr: np.ndarray, pts: list,
                   P: np.ndarray, D: np.ndarray, M: np.ndarray, offset: tuple[float, float], f_px: float) -> None:
    """測定中のフレームごとの画像（手の点と、点のまわりの距離を、写真と深度の上に描く）"""
    import try_image as dp_try  # Depth Pro 側の描き方

    zs = {}
    for p in dp.DEPTH_POINTS:
        u, v = pts[p][0] - offset[0], pts[p][1] - offset[1]
        q = mb.patch_point(mb.extract_patch3(P, u, v), dp.extract_patch(M, u, v), 3.0)
        zs[p] = float(q[2]) if q is not None else float("nan")
    if not all(math.isfinite(z) for z in zs.values()):
        return
    # 長さは④で集計して出すので、ここでは点と距離だけを描く
    local = [[x - offset[0], y - offset[1]] for x, y in pts]
    if offset != (0.0, 0.0):  # 条件B：切り抜いた範囲だけを描く
        x0, y0 = int(offset[0]), int(offset[1])
        bgr = bgr[y0:y0 + D.shape[0], x0:x0 + D.shape[1]]
    overlay = bgr.copy()
    for a, b in dp_try.HAND_EDGES:
        cv2.line(overlay, tuple(round(v) for v in local[a]), tuple(round(v) for v in local[b]), (255, 255, 255), 1, cv2.LINE_AA)
    s = max(overlay.shape[:2]) / 1280
    dp_try.draw_points(overlay, local, zs, s)
    dp_try.put_text(overlay, f"{rec_id} {model_key} {cond} #{idx}  f={f_px:.0f}px", (12, round(30 * max(s, 0.5))), 0.7 * max(s, 0.5))
    depth_vis = dp_try.draw_depth(np.where(np.isfinite(D), D, np.nan), local, zs)
    out = mb.DATA / "vis" / rec_id / f"{model_key}_{cond}_{idx:03d}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), np.hstack([overlay, depth_vis]), [cv2.IMWRITE_JPEG_QUALITY, 85])


def run(rec_id: str, model_key: str, cond: str, backend, force: bool, save_vis: bool = False) -> None:
    out_npz = mb.DATA / "points" / rec_id / f"{model_key}_{cond}.npz"
    out_json = out_npz.with_suffix(".json")
    if out_json.exists() and not force:
        print(f"{rec_id} {model_key} {cond}: 推定済み（作り直すなら --force）")
        return
    fdir = dp.DATA / "frames" / rec_id
    frames = {f["index"]: f for f in dp.load_json(fdir / "frames.json")["frames"]}
    lms = [r for r in dp.load_json(dp.DATA / "landmarks" / f"{rec_id}.json")["frames"] if r["used"]]
    rec = next((r for r in dp.recordings() if r["rec_id"] == rec_id), {})

    arrays: dict[str, np.ndarray] = {}
    rows = []
    for lm in lms:
        fr = frames[lm["index"]]
        w, h = fr["width"], fr["height"]
        rgb = cv2.cvtColor(cv2.imread(str(fdir / f"{fr['index']:03d}.jpg")), cv2.COLOR_BGR2RGB)
        pts = lm["points_px"]
        row = {"index": fr["index"]}
        if cond in ("A", "C"):
            fov_x = None
            if cond == "C":
                f35 = dp.to_float(rec.get("focal_35mm_mm"))
                if not math.isfinite(f35):
                    print(f"{rec_id}: recordings.csv に focal_35mm_mm がないので、条件Cを飛ばします")
                    return
                fov_x = mb.fov_x_from_f_px(dp.f_px_from_35mm(f35, w, h), w)
            r = backend.infer(rgb, fov_x)
            row.update(f_px=r.f_px, f_source="device" if fov_x else "model", infer_s=round(r.infer_s, 4))
            P, D, M = r.points_mm, r.depth_mm, r.mask.astype(np.float32)
            offset = (0.0, 0.0)
        elif cond == "B":
            x0, y0, x1, y1 = dp.crop_box(pts, w, h)
            x0, y0, x1, y1 = int(math.floor(x0)), int(math.floor(y0)), int(math.ceil(x1)), int(math.ceil(y1))
            cw, ch = x1 - x0, y1 - y0
            s = dp.CROP_LONG_SIDE / max(cw, ch)
            small = cv2.resize(rgb[y0:y1, x0:x1], (max(1, round(cw * s)), max(1, round(ch * s))), interpolation=cv2.INTER_AREA)
            r = backend.infer(small, None)
            # 点群は切り抜いた画像の中心を原点にした座標で返る（長さは2点の差なので影響は小さい。scripts.md §4）
            P = resize_to(r.points_mm, cw, ch)
            D = resize_to(r.depth_mm, cw, ch)
            M = resize_to(r.mask.astype(np.float32), cw, ch)
            row.update(f_px=dp.f_crop_to_orig(r.f_px, max(cw, ch)), f_source="model", infer_s=round(r.infer_s, 4),
                       crop=[x0, y0, x1, y1])
            offset = (float(x0), float(y0))
        else:
            raise SystemExit(f"知らない条件です：{cond}")
        if save_vis:
            save_frame_vis(rec_id, model_key, cond, fr["index"], cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), pts, P, D, M,
                           offset, row["f_px"])
        for p in dp.DEPTH_POINTS:
            u, v = pts[p][0] - offset[0], pts[p][1] - offset[1]
            key = f"f{fr['index']:03d}_p{p}"
            arrays[f"{key}_points"] = mb.extract_patch3(P, u, v)
            arrays[f"{key}_depth"] = dp.extract_patch(D, u, v)
            arrays[f"{key}_mask"] = dp.extract_patch(M, u, v)
        rows.append(row)

    out_npz.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out_npz, **arrays)
    dp.save_json(out_json, {"rec_id": rec_id, "model": backend.name, "model_version": backend.version, "cond": cond,
                            "device": backend.device_name(), "frames": rows})
    t = dp.median(r["infer_s"] for r in rows)
    print(f"{rec_id} {model_key} {cond}: {len(rows)} 枚を推定（1枚 {t:.2f} 秒、{backend.device_name()}）")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rec")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--model", default="vitl", choices=["vitl", "vits", "constant"])
    ap.add_argument("--cond", default="A")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--save-vis", action="store_true", help="フレームごとの画像を data/vis/{撮影ID}/ に保存する")
    a = ap.parse_args(argv)
    ids = dp.rec_ids(a.rec, a.all)
    backend = mb.make_backend(a.model)
    for rid in ids:
        for c in a.cond.split(","):
            run(rid, a.model, c.strip().upper(), backend, a.force, a.save_vis)


if __name__ == "__main__":
    sys.exit(main())
