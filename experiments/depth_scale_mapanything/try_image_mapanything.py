r"""写真1枚で、MapAnything の距離推定を試し、途中経過の画像を保存する（docs/depth-scale-mapanything/scripts.md §3）。

使い方：..\depth_scale\.venv\Scripts\python try_image_mapanything.py <写真> [--compare-depth-pro] [--truth 0→5,0→9,0→17,5→17]
正解は既定で写真1の Depth Pro の値（本人が定規で確かめて正確と確認済み）。
注意：写真はどこにも保存しない。結果の画像と数値だけを data/vis/ に保存する（コミットしない）。
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import cv2
import numpy as np

import mapanything_backend as mab
from mapanything_backend import dp
import landmarks as dp_landmarks  # Depth Pro 側の MediaPipe の呼び方
import moge_backend as mb         # MoGe-2 側の点のまわりの3D位置の取り方・マスクの描き方
import try_image as dp_try        # Depth Pro 側の画像の描き方

TRUTH = {"seg_0_5_mm": 75.5, "seg_0_9_mm": 72.3, "seg_0_17_mm": 69.3, "seg_5_17_mm": 61.8}
SEG_SHORT = {"seg_0_5_mm": "0→5", "seg_0_9_mm": "0→9", "seg_0_17_mm": "0→17", "seg_5_17_mm": "5→17"}


def measure(r: mab.Result, pts: list, radius: float) -> tuple[dict, dict, dict]:
    """点群から（本命）と、深度とカメラの情報から（確かめ）の4区間の長さと、5点の距離"""
    h, w = r.depth_mm.shape
    m = r.mask.astype(np.float32)
    xyz, xyz_d, zs = {}, {}, {}
    for p in dp.DEPTH_POINTS:
        q = mb.patch_point(mb.extract_patch3(r.points_mm, *pts[p]), dp.extract_patch(m, *pts[p]), radius)
        d = dp.extract_patch(r.depth_mm, *pts[p])
        d[np.nan_to_num(dp.extract_patch(m, *pts[p]), nan=0.0) <= 0.5] = np.nan
        z = dp.patch_depth(d, radius)
        if q is None or z is None:
            raise SystemExit(f"点 {p} の3D位置が出ませんでした（使えない画素の上にある）")
        xyz[p], zs[p] = q, float(q[2])
        xyz_d[p] = dp.backproject(*pts[p], z, r.f_px, w / 2, h / 2)
    L = {k: float(np.linalg.norm(xyz[a] - xyz[b])) for k, (a, b) in dp.SEGMENTS.items()}
    Ld = {k: float(np.linalg.norm(xyz_d[a] - xyz_d[b])) for k, (a, b) in dp.SEGMENTS.items()}
    return L, Ld, zs


# ---------- 途中経過の画像 ----------

def img_input(rgb: np.ndarray, pts: list) -> np.ndarray:
    img = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    s = max(img.shape[:2]) / 1280
    for a, b in dp_try.HAND_EDGES:
        cv2.line(img, tuple(round(v) for v in pts[a]), tuple(round(v) for v in pts[b]), (255, 255, 255), 1, cv2.LINE_AA)
    for i, (x, y) in enumerate(pts):
        cv2.circle(img, (round(x), round(y)), 3 if i not in dp.DEPTH_POINTS else 5,
                   (0, 255, 255) if i not in dp.DEPTH_POINTS else (0, 0, 255), -1, cv2.LINE_AA)
    dp_try.put_text(img, f"1 input seen by model {img.shape[1]}x{img.shape[0]}", (8, 24), max(0.5, 0.6 * s))
    return img


def img_conf(conf: np.ndarray, pts: list) -> np.ndarray:
    c = np.nan_to_num(conf, nan=0.0)
    lo, hi = np.percentile(c, 2), np.percentile(c, 98)
    img = cv2.applyColorMap((255 * np.clip((c - lo) / max(hi - lo, 1e-6), 0, 1)).astype(np.uint8), cv2.COLORMAP_VIRIDIS)
    for p in dp.DEPTH_POINTS:
        mb.cv2_circle(img, pts[p])
    dp_try.put_text(img, f"3 confidence (yellow=high) {lo:.2f}-{hi:.2f}", (8, 24), 0.55)
    return img


def img_side(points_mm: np.ndarray, mask: np.ndarray, pts: list, zs: dict, size: tuple[int, int]) -> np.ndarray:
    """手の部分の点群を真横から見た図（横＝左右 x、縦＝奥行き z）。手が板のように正しい奥行きに並ぶか"""
    w, h = size
    canvas = np.full((h, w, 3), 30, np.uint8)
    x0, y0, x1, y1 = (int(v) for v in dp.crop_box(pts, mask.shape[1], mask.shape[0]))
    P = points_mm[y0:y1, x0:x1].reshape(-1, 3)
    P = P[np.all(np.isfinite(P), axis=1)]
    if len(P) == 0:
        return canvas
    xs, zz = P[:, 0], P[:, 2]
    xmin, xmax = np.percentile(xs, 1), np.percentile(xs, 99)
    zmin, zmax = np.percentile(zz, 1) - 20, np.percentile(zz, 99) + 20
    def to_px(x, z):  # noqa: E306
        return int((x - xmin) / max(xmax - xmin, 1e-6) * (w - 60) + 30), int((z - zmin) / max(zmax - zmin, 1e-6) * (h - 80) + 50)
    sel = P[np.random.default_rng(0).choice(len(P), size=min(len(P), 20000), replace=False)]
    for x, _, z in sel:
        u, v = to_px(x, z)
        if 0 <= u < w and 0 <= v < h:
            canvas[v, u] = (200, 200, 200)
    xyz = {p: points_mm[int(round(pts[p][1])), int(round(pts[p][0]))] for p in dp.DEPTH_POINTS}
    for p, q in xyz.items():
        if np.all(np.isfinite(q)):
            u, v = to_px(q[0], q[2])
            cv2.circle(canvas, (u, v), 6, (0, 0, 255), -1, cv2.LINE_AA)
            dp_try.put_text(canvas, f"P{p} {zs[p]:.0f}mm", (u + 8, v - 6), 0.45)
    dp_try.put_text(canvas, "5 side view of hand points (x: left-right, y: depth, down=far)", (8, 24), 0.5)
    dp_try.put_text(canvas, f"depth {zmin:.0f}-{zmax:.0f}mm", (8, h - 12), 0.5)
    return canvas


VIEW_LONG = 1280  # 見るための画像は、長い辺をこの大きさまで拡大してから描く（モデルが見た画像は 518px と小さいため）


def enlarge(img: np.ndarray, pts: list) -> tuple[np.ndarray, list, float]:
    """画像を長い辺 VIEW_LONG まで拡大し、点の位置も同じ割合で直す"""
    s = VIEW_LONG / max(img.shape[:2])
    if s <= 1.0:
        return img, pts, 1.0
    big = cv2.resize(img, (round(img.shape[1] * s), round(img.shape[0] * s)), interpolation=cv2.INTER_CUBIC)
    return big, [[x * s, y * s] for x, y in pts], s


def img_result(rgb, pts, zs, L, f_px, truth) -> np.ndarray:
    """最終結果：拡大した画像に4区間の線と長さを描き、下に数値の表を付ける"""
    big, bpts, s = enlarge(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), pts)
    img = dp_try.draw_overlay(big, bpts, zs, L, f_px * s)
    w = img.shape[1]
    rows = [("segment", "MapAnything", "truth", "error")] + [
        (SEG_SHORT[k].replace("→", "->"), f"{L[k]:.1f} mm", f"{truth[k]:.1f} mm", f"{(L[k] / truth[k] - 1) * 100:+.0f}%")
        for k in dp.SEGMENTS]
    dev = dp.deviation_pct(dp.scale_ratio(L, truth))
    line_h, pad = 46, 24
    panel = np.full((pad * 2 + line_h * (len(rows) + 1), w, 3), 25, np.uint8)
    cols = [pad, int(w * 0.30), int(w * 0.58), int(w * 0.82)]
    for i, row in enumerate(rows):
        y = pad + line_h * (i + 1) - 12
        for j, cell in enumerate(row):
            color = (200, 200, 200) if i == 0 else (0, 220, 255) if j == 3 else (255, 255, 255)
            cv2.putText(panel, cell, (cols[j], y), cv2.FONT_HERSHEY_SIMPLEX, 0.95, color, 2, cv2.LINE_AA)
    verdict = "PASS" if abs(dev) <= 2.0 else "FAIL"
    cv2.putText(panel, f"median error {dev:+.0f}%  ->  {verdict} (target: within +-2%)",
                (pad, pad + line_h * (len(rows) + 1) - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.95,
                (80, 220, 80) if verdict == "PASS" else (80, 80, 255), 2, cv2.LINE_AA)
    return np.vstack([img, panel])


def save_images(stem: str, r: mab.Result, pts, zs, L, truth) -> dict:
    out = mab.DATA / "vis"
    out.mkdir(parents=True, exist_ok=True)
    h, w = r.depth_mm.shape
    images = {
        "1_input": img_input(r.rgb, pts),
        "2_depth": dp_try.draw_depth(np.where(np.isfinite(r.depth_mm), r.depth_mm, np.nan), pts, zs),
        "3_conf": img_conf(r.conf, pts),
        "4_mask": mb.draw_mask(cv2.cvtColor(r.rgb, cv2.COLOR_RGB2BGR), r.mask, pts),
        "5_side": img_side(r.points_mm, r.mask, pts, zs, (w, h)),
        "6_result": img_result(r.rgb, pts, zs, L, r.f_px, truth),
    }
    dp_try.put_text(images["2_depth"], "2 depth", (8, h - 12), 0.6)
    dp_try.put_text(images["4_mask"], "4 mask: red = not usable", (8, 24), 0.6)
    # まとめ画像：どのタイルも同じ大きさ（モデルが見た画像の2倍）にそろえて並べる
    tw, th = w * 2, h * 2
    tiles = [cv2.resize(t, (tw, th), interpolation=cv2.INTER_CUBIC) for t in list(images.values())[:5]]
    tiles.append(cv2.resize(images["6_result"], (tw, round(images["6_result"].shape[0] * tw / images["6_result"].shape[1]))))
    tiles[5] = tiles[5][:th] if tiles[5].shape[0] >= th else np.vstack([tiles[5], np.zeros((th - tiles[5].shape[0], tw, 3), np.uint8)])
    images["grid"] = np.vstack([np.hstack(tiles[0:3]), np.hstack(tiles[3:6])])
    paths = {}
    for k, img in images.items():
        paths[k] = out / f"{stem}_mapanything_{k}.jpg"
        cv2.imwrite(str(paths[k]), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return paths


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", type=Path)
    ap.add_argument("--truth", help="正解（mm）を 0→5,0→9,0→17,5→17 の順に。既定は写真1の Depth Pro の値")
    ap.add_argument("--radius", type=float, default=3.0)
    ap.add_argument("--max-long-side", type=int, default=1280)
    ap.add_argument("--landmarker", type=Path, default=dp_landmarks.DEFAULT_MODEL)
    ap.add_argument("--compare-depth-pro", action="store_true")
    ap.add_argument("--constant", action="store_true", help="重みなしで流れだけを確かめる偽物を使う")
    ap.add_argument("--no-save", action="store_true")
    a = ap.parse_args(argv)
    truth = dict(TRUTH)
    if a.truth:
        vals = [float(x) for x in a.truth.split(",")]
        if len(vals) != 4:
            raise SystemExit("--truth は 0→5,0→9,0→17,5→17 の4つを mm で")
        truth = dict(zip(dp.SEGMENTS, vals))

    bgr = cv2.imread(str(a.image))
    if bgr is None:
        raise SystemExit(f"{a.image} を読めませんでした")
    h0, w0 = bgr.shape[:2]
    s = min(1.0, a.max_long_side / max(w0, h0))
    if s < 1.0:
        bgr = cv2.resize(bgr, (round(w0 * s), round(h0 * s)), interpolation=cv2.INTER_AREA)
    H, W = bgr.shape[:2]
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

    print("MapAnything を読み込んでいます（初回は重みを取ってくるので時間がかかります）…")
    backend = mab.ConstantBackend() if a.constant else mab.MapAnythingBackend()
    r = backend.infer(rgb)
    h, w = r.depth_mm.shape

    # MediaPipe は、モデルが実際に見た画像（縮めて切り取ったもの）にかける
    mp, lmk = dp_landmarks.create_landmarker(a.landmarker)
    used, reason, pts = dp_landmarks.judge(lmk.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(r.rgb))).hand_landmarks, w, h)
    if pts is None:
        raise SystemExit(f"モデルが見た画像で、手の21点が取れませんでした（{reason}）")
    if not used:
        print(f"注意：{reason}（モデルが見た画像で、手が端にかかっている）。結果は参考程度に")

    L, Ld, zs = measure(r, pts, a.radius)
    f_orig = mab.focal_to_original(r.f_px, (W, H), (w, h))
    ratio = dp.scale_ratio(L, truth)
    other = None
    dpj = dp.DATA / "vis" / f"{a.image.stem}_depthpro.json"
    if a.compare_depth_pro and dpj.exists():
        other = dp.load_json(dpj)

    print()
    print(f"元の画像：{W}×{H}px　モデルが見た画像：{w}×{h}px　推論：{r.infer_s:.2f} 秒（{backend.device_name()}）　倍率（metric_scaling_factor）：{r.scale:.3f}")
    print(f"焦点距離：{r.f_px:.0f}px（モデルが見た画像）→ 元の画像でおよそ {f_orig:.0f}px"
          + (f"　Depth Pro：{other['f_px']:.0f}px" if other else ""))
    print(f"カメラから手首まで：{zs[0]:.0f}mm　中指の付け根まで：{zs[9]:.0f}mm"
          + (f"　Depth Pro：{other['z_mm']['0']:.0f}mm・{other['z_mm']['9']:.0f}mm" if other else ""))
    print()
    print("| 区間 | 正解 | MapAnything | ずれ | 確かめ（深度から） |" + (" Depth Pro |" if other else ""))
    print("|---|---|---|---|---|" + ("---|" if other else ""))
    for k in dp.SEGMENTS:
        print(f"| {SEG_SHORT[k]} | {truth[k]:.1f} | {L[k]:.1f} | {(L[k] / truth[k] - 1) * 100:+.1f}% | {Ld[k]:.1f} |"
              + (f" {other['lengths_mm'][k]:.1f} |" if other else ""))
    dev = dp.deviation_pct(ratio)
    worst = max(abs(L[k] / truth[k] - 1) for k in dp.SEGMENTS) * 100
    ok = abs(dev) <= 2.0 and worst <= 4.0
    print()
    print(f"ずれの中央値：{dev:+.1f}%　最大：{worst:.1f}%　→ {'合格' if ok else '不合格'}（目安：中央値 ±2% 以内・最大 ±4% 以内）")
    print(f"点群と深度の長さの差：最大 {max(abs(L[k] / Ld[k] - 1) for k in dp.SEGMENTS) * 100:.2f}%")

    if not a.no_save:
        paths = save_images(a.image.stem, r, pts, zs, L, truth)
        dp.save_json(mab.DATA / "vis" / f"{a.image.stem}_mapanything.json", {
            "model": backend.repo, "image": a.image.name, "width": W, "height": H, "model_wh": [w, h],
            "f_px_model": r.f_px, "f_px": f_orig, "scale": r.scale, "infer_s": r.infer_s, "radius_px": a.radius,
            "z_mm": {str(p): z for p, z in zs.items()}, "lengths_mm": L, "lengths_from_depth_mm": Ld,
            "truth_mm": truth, "deviation_pct": dev, "pass": ok})
        print()
        print("途中経過の画像を保存しました（data/ の中なのでコミットされません）：")
        for k, p in paths.items():
            print(f"  {k}: {p}")


if __name__ == "__main__":
    sys.exit(main())
