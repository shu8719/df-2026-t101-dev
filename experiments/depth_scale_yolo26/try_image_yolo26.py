r"""写真1枚で、YOLO26 Depth（大きさ × 焦点距離の出どころ）の手の甲の4区間を出し、画像を保存する
（docs/depth-scale-yolo26/scripts.md §3）。

使い方：..\depth_scale\.venv\Scripts\python try_image_yolo26.py <写真> [--models n,s,m,l,x] [--focals exif,fixed26,depthpro,moge2]
正解は写真1の Depth Pro の値（本人が定規で確かめた値）。写真はどこにも保存しない（結果の画像と数値だけ data/vis/ に）。
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import cv2
import numpy as np

import focal as fc
import yolo26_backend as yb
from yolo26_backend import dp
import landmarks as dp_landmarks  # Depth Pro 側の MediaPipe の呼び方
import try_image as dp_try        # Depth Pro 側の画像の描き方

TRUTH = {"seg_0_5_mm": 75.5, "seg_0_9_mm": 72.3, "seg_0_17_mm": 69.3, "seg_5_17_mm": 61.8}
SEG = {"seg_0_5_mm": "0-5", "seg_0_9_mm": "0-9", "seg_0_17_mm": "0-17", "seg_5_17_mm": "5-17"}


def lengths(depth_mm: np.ndarray, pts: list, f_px: float, radius: float = 3.0) -> tuple[dict, dict]:
    h, w = depth_mm.shape
    xyz, zs = {}, {}
    for p in dp.DEPTH_POINTS:
        z = dp.patch_depth(dp.extract_patch(depth_mm, *pts[p]), radius)
        if z is None:
            raise SystemExit(f"点 {p} の距離が出ませんでした")
        zs[p] = z
        xyz[p] = dp.backproject(*pts[p], z, f_px, w / 2, h / 2)
    return {k: float(np.linalg.norm(xyz[a] - xyz[b])) for k, (a, b) in dp.SEGMENTS.items()}, zs


def deviation(L: dict, truth: dict) -> float:
    return dp.deviation_pct(dp.scale_ratio(L, truth))


# ---------- 画像 ----------

def enlarge(img, pts, long_side=1280):
    s = long_side / max(img.shape[:2])
    if abs(s - 1) < 1e-3:
        return img, pts, 1.0
    big = cv2.resize(img, (round(img.shape[1] * s), round(img.shape[0] * s)), interpolation=cv2.INTER_CUBIC)
    return big, [[x * s, y * s] for x, y in pts], s


def img_input(bgr, pts):
    img, bp, s = enlarge(bgr, pts)
    for a, b in dp_try.HAND_EDGES:
        cv2.line(img, tuple(round(v) for v in bp[a]), tuple(round(v) for v in bp[b]), (255, 255, 255), 2, cv2.LINE_AA)
    for i, (x, y) in enumerate(bp):
        big = i in dp.DEPTH_POINTS
        cv2.circle(img, (round(x), round(y)), 8 if big else 5, (0, 0, 255) if big else (0, 255, 255), -1, cv2.LINE_AA)
    dp_try.put_text(img, "1 input + hand points (red = used for length)", (16, 40), 1.0)
    return img


def img_depth(depth_mm, pts, zs, label):
    img, bp, _ = enlarge(dp_try.draw_depth(depth_mm, pts, zs), pts)
    dp_try.put_text(img, f"2 depth ({label})", (16, img.shape[0] - 20), 1.0)
    return img


def img_result(bgr, pts, zs, L, f_px, table, truth, label):
    """拡大した写真に4区間の線と長さ（代表の組み合わせ）、下に「大きさ × 出どころ」のずれの表"""
    big, bp, s = enlarge(bgr, pts)
    img = dp_try.draw_overlay(big, bp, zs, L, f_px * s)
    dp_try.put_text(img, f"3 result: {label}  median error {deviation(L, truth):+.1f}%", (16, img.shape[0] - 20), 1.0, (0, 255, 255))
    focals = sorted({f for _, f in table})
    sizes = [m for m in yb.SIZES if any(k[0] == m for k in table)]
    w = img.shape[1]
    lh, pad = 44, 20
    panel = np.full((pad * 2 + lh * (len(sizes) + 2), w, 3), 25, np.uint8)
    cw = (w - 160) // max(1, len(focals))
    cv2.putText(panel, "median error vs truth (target +-2%)", (pad, pad + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (200, 200, 200), 2, cv2.LINE_AA)
    for j, f in enumerate(focals):
        cv2.putText(panel, f, (160 + j * cw, pad + lh + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (200, 200, 200), 2, cv2.LINE_AA)
    for i, m in enumerate(sizes):
        y = pad + lh * (i + 2) + 28
        cv2.putText(panel, f"yolo26{m}", (pad, y), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (255, 255, 255), 2, cv2.LINE_AA)
        for j, f in enumerate(focals):
            if (m, f) in table:
                d = table[(m, f)]
                col = (80, 220, 80) if abs(d) <= 2 else (0, 200, 255) if abs(d) <= 10 else (80, 80, 255)
                cv2.putText(panel, f"{d:+.1f}%", (160 + j * cw, y), cv2.FONT_HERSHEY_SIMPLEX, 0.85, col, 2, cv2.LINE_AA)
    return np.vstack([img, panel])


def save_images(stem, bgr, pts, depth_mm, zs, L, f_px, table, truth, label):
    out = yb.DATA / "vis"
    out.mkdir(parents=True, exist_ok=True)
    a, b, c = img_input(bgr, pts), img_depth(depth_mm, pts, zs, label.split(" ")[0]), img_result(bgr, pts, zs, L, f_px, table, truth, label)
    h = max(a.shape[0], b.shape[0], c.shape[0])
    pad = lambda x: np.vstack([x, np.zeros((h - x.shape[0], x.shape[1], 3), np.uint8)])  # noqa: E731
    paths = {}
    for k, img in {"1_input": a, "2_depth": b, "3_result": c, "grid": np.hstack([pad(a), pad(b), pad(c)])}.items():
        paths[k] = out / f"{stem}_yolo26_{k}.jpg"
        cv2.imwrite(str(paths[k]), img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return paths


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", type=Path)
    ap.add_argument("--models", default="n,s,m,l,x")
    ap.add_argument("--focals", default=",".join(fc.SOURCES))
    ap.add_argument("--max-long-side", type=int, default=1280)
    ap.add_argument("--landmarker", type=Path, default=dp_landmarks.DEFAULT_MODEL)
    ap.add_argument("--constant", action="store_true", help="重みなしで流れだけを確かめる偽物")
    ap.add_argument("--no-save", action="store_true")
    a = ap.parse_args(argv)
    sizes = [m.strip() for m in a.models.split(",") if m.strip()]

    bgr = cv2.imread(str(a.image))  # 撮影情報の向きどおりに回して読む
    if bgr is None:
        raise SystemExit(f"{a.image} を読めませんでした")
    s = min(1.0, a.max_long_side / max(bgr.shape[:2]))
    if s < 1.0:
        bgr = cv2.resize(bgr, (round(bgr.shape[1] * s), round(bgr.shape[0] * s)), interpolation=cv2.INTER_AREA)
    H, W = bgr.shape[:2]
    mp, lmk = dp_landmarks.create_landmarker(a.landmarker)
    used, reason, pts = dp_landmarks.judge(
        lmk.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))).hand_landmarks, W, H)
    if pts is None:
        raise SystemExit(f"手の21点が取れませんでした（{reason}）")
    focals = {f: fc.focal(f, a.image, (W, H)) for f in a.focals.split(",")}
    focals = {f: v for f, v in focals.items() if v}
    if not focals:
        raise SystemExit("使える焦点距離がありません")

    results, table, depths = {}, {}, {}
    for m in sizes:
        model = yb.ConstantDepth() if a.constant else yb.Yolo26Depth(m)
        d, t = model.depth_mm(bgr)
        depths[m] = d
        for f, fpx in focals.items():
            L, zs = lengths(d, pts, fpx)
            results[f"{m}_{f}"] = {"size": m, "focal": f, "f_px": fpx, "infer_s": t, "lengths_mm": L,
                                   "z_mm": {str(p): z for p, z in zs.items()}, "deviation_pct": deviation(L, TRUTH)}
            table[(m, f)] = deviation(L, TRUTH)

    print(f"画像：{W}×{H}px　手の点：{'OK' if used else reason}")
    print("焦点距離（px）：" + "、".join(f"{f} {v:.0f}" for f, v in focals.items()))
    print("| 大きさ | " + " | ".join(focals) + " | 手首までの距離 |")
    print("|---" * (len(focals) + 2) + "|")
    for m in sizes:
        z0 = results[f"{m}_{next(iter(focals))}"]["z_mm"]["0"]
        print(f"| yolo26{m} | " + " | ".join(f"{table[(m, f)]:+.1f}%" for f in focals) + f" | {z0:.0f}mm |")

    if not a.no_save:
        rep_f = "exif" if "exif" in focals else "fixed26" if "fixed26" in focals else next(iter(focals))
        rep_m = "x" if "x" in sizes else sizes[-1]
        r = results[f"{rep_m}_{rep_f}"]
        zs = {int(p): z for p, z in r["z_mm"].items()}
        paths = save_images(a.image.stem, bgr, pts, depths[rep_m], zs, r["lengths_mm"], r["f_px"], table, TRUTH,
                            f"yolo26{rep_m} + {rep_f}")
        dp.save_json(yb.DATA / "vis" / f"{a.image.stem}_yolo26.json", {
            "image": a.image.name, "width": W, "height": H, "hand_ok": used, "focals_px": focals, "results": results})
        print(f"画像：{paths['grid']}")


if __name__ == "__main__":
    sys.exit(main())
