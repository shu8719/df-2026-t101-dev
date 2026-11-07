r"""写真1枚で、AIの距離推定を試す（手軽な確かめ用。実験の本番は ①〜⑤ の流れで行う）。

手の甲を上にした写真を渡すと、MediaPipe の手首と指の付け根の点に、Depth Pro の深度と焦点距離を組み合わせて、
カメラから手までの距離と、手の甲の4区間の長さ（mm）を表示する。定規やノギスで測った値と比べる。

使い方：.venv\Scripts\python try_image.py <写真のパス> [--radius 3] [--skin-offset-mm 0]
注意：写真はどこにも保存しない。Depth Pro の重みは研究目的だけのライセンスなので、この実験にだけ使う。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

import common
import depth as depth_mod
import landmarks as lm_mod

NAMES = {
    "seg_0_5_mm": "手首 → 人差し指の付け根",
    "seg_0_9_mm": "手首 → 中指の付け根",
    "seg_0_17_mm": "手首 → 小指の付け根",
    "seg_5_17_mm": "人差し指の付け根 → 小指の付け根",
}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", type=Path)
    ap.add_argument("--radius", type=float, default=3.0)
    ap.add_argument("--skin-offset-mm", type=float, default=0.0)
    ap.add_argument("--max-long-side", type=int, default=1280, help="本番のフレームと同じく、長い辺をこの大きさまで縮める")
    ap.add_argument("--landmarker", type=Path, default=lm_mod.DEFAULT_MODEL)
    ap.add_argument("--checkpoint", type=Path, default=common.HERE / "checkpoints" / "depth_pro.pt")
    ap.add_argument("--no-save", action="store_true", help="結果の画像（data/vis/）を保存しない")
    a = ap.parse_args(argv)

    bgr = cv2.imread(str(a.image))
    if bgr is None:
        raise SystemExit(f"{a.image} を読めませんでした")
    h0, w0 = bgr.shape[:2]
    s = min(1.0, a.max_long_side / max(w0, h0))
    if s < 1.0:
        bgr = cv2.resize(bgr, (round(w0 * s), round(h0 * s)), interpolation=cv2.INTER_AREA)
    h, w = bgr.shape[:2]
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

    mp, lmk = lm_mod.create_landmarker(a.landmarker)
    res = lmk.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
    used, reason, pts = lm_mod.judge(res.hand_landmarks, w, h)
    if pts is None:
        raise SystemExit(f"手の21点が取れませんでした（{reason}）")
    if not used:
        print(f"注意：{reason}（手が画面の端にかかっている）。点がずれやすいので、結果は参考程度に")

    print("Depth Pro を読み込んでいます（初回は時間がかかります）…")
    backend = depth_mod.make_backend("depth_pro", a.checkpoint)
    t0 = time.perf_counter()
    dmap, f_px = backend.infer(rgb, None)
    dt = time.perf_counter() - t0
    dmap = depth_mod.resize_to(dmap, w, h)

    zs = {}
    for p in common.DEPTH_POINTS:
        z = common.patch_depth(common.extract_patch(dmap, *pts[p]), a.radius)
        if z is None:
            raise SystemExit(f"点 {p} の深度が出ませんでした")
        zs[p] = z + a.skin_offset_mm
    xyz = {p: common.backproject(*pts[p], zs[p], f_px, w / 2, h / 2) for p in zs}

    print()
    print(f"画像：{w}×{h}px　推論：{dt:.2f} 秒（{backend.device_name()}）")
    print(f"推定した焦点距離：{f_px:.0f}px（35mm換算でおよそ {f_px * 43.27 / (w ** 2 + h ** 2) ** 0.5:.0f}mm）")
    print(f"カメラから手首まで：{zs[0]:.0f}mm　中指の付け根まで：{zs[9]:.0f}mm")
    print()
    print("手の甲の4区間（AIの推定）")
    lengths = {}
    for k, (pa, pb) in common.SEGMENTS.items():
        lengths[k] = float(((xyz[pa] - xyz[pb]) ** 2).sum() ** 0.5)
        print(f"  {NAMES[k]}：{lengths[k]:.1f}mm")
    print()
    print("定規やノギスで同じ所を測って比べてください（手首はしわの真ん中、付け根は関節の山）。")
    print("AIの深度は皮膚の表面までなので、関節の中心より数%短く出る見込みです（--skin-offset-mm で試せます）。")

    if not a.no_save:
        out_dir = common.DATA / "vis"
        out_dir.mkdir(parents=True, exist_ok=True)
        overlay = draw_overlay(bgr, pts, zs, lengths, f_px)
        dvis = draw_depth(dmap, pts, zs)
        paths = {
            "overlay": out_dir / f"{a.image.stem}_overlay.jpg",
            "depth": out_dir / f"{a.image.stem}_depth.jpg",
            "side": out_dir / f"{a.image.stem}_side.jpg",
        }
        cv2.imwrite(str(paths["overlay"]), overlay, [cv2.IMWRITE_JPEG_QUALITY, 92])
        cv2.imwrite(str(paths["depth"]), dvis, [cv2.IMWRITE_JPEG_QUALITY, 92])
        cv2.imwrite(str(paths["side"]), np.hstack([overlay, dvis]), [cv2.IMWRITE_JPEG_QUALITY, 92])
        print()
        print("画像を保存しました（data/ の中なのでコミットされません）：")
        for p in paths.values():
            print(f"  {p}")


# ---------- 画像に描く（文字はフォントの都合で英数字だけ） ----------

SEG_COLORS = {"seg_0_5_mm": (0, 200, 255), "seg_0_9_mm": (0, 255, 0), "seg_0_17_mm": (255, 128, 0), "seg_5_17_mm": (255, 0, 255)}
HAND_EDGES = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11), (11, 12),
              (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (17, 18), (18, 19), (19, 20), (0, 17)]


def put_text(img: np.ndarray, text: str, org: tuple[int, int], scale: float, color=(255, 255, 255)) -> None:
    """読みやすいように、黒いふちを付けて文字を描く"""
    th = max(1, round(scale * 2))
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), th + 3, cv2.LINE_AA)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, th, cv2.LINE_AA)


def draw_points(img: np.ndarray, pts: list, zs: dict[int, float], scale: float) -> None:
    for p, z in zs.items():
        x, y = (round(v) for v in pts[p])
        cv2.circle(img, (x, y), max(4, round(7 * scale)), (0, 0, 255), -1, cv2.LINE_AA)
        cv2.circle(img, (x, y), max(4, round(7 * scale)), (255, 255, 255), 2, cv2.LINE_AA)
        put_text(img, f"P{p} {z:.0f}mm", (x + 10, y - 10), 0.5 * scale)


def draw_overlay(bgr: np.ndarray, pts: list, zs: dict[int, float], lengths: dict[str, float], f_px: float) -> np.ndarray:
    img = bgr.copy()
    h, w = img.shape[:2]
    scale = max(w, h) / 1280
    for a, b in HAND_EDGES:  # 手の骨組み（細い白線）
        cv2.line(img, tuple(round(v) for v in pts[a]), tuple(round(v) for v in pts[b]), (255, 255, 255), 1, cv2.LINE_AA)
    for k, (pa, pb) in common.SEGMENTS.items():  # 手の甲の4区間（太い色線と長さ）
        p1, p2 = (tuple(round(v) for v in pts[i]) for i in (pa, pb))
        cv2.line(img, p1, p2, SEG_COLORS[k], max(2, round(4 * scale)), cv2.LINE_AA)
        mid = ((p1[0] + p2[0]) // 2 + 8, (p1[1] + p2[1]) // 2)
        put_text(img, f"{pa}-{pb} {lengths[k]:.1f}mm", mid, 0.6 * scale, SEG_COLORS[k])
    draw_points(img, pts, zs, scale)
    lines = [f"f = {f_px:.0f}px", f"wrist {zs[0]:.0f}mm / MCP9 {zs[9]:.0f}mm from camera"]
    for i, t in enumerate(lines):
        put_text(img, t, (12, round(30 * scale) + i * round(30 * scale)), 0.7 * scale)
    return img


def draw_depth(dmap: np.ndarray, pts: list, zs: dict[int, float]) -> np.ndarray:
    """深度を色で表す。手のまわりが見分けやすいよう、5点の深度の前後で色の幅を決める（近い＝赤、遠い＝青）"""
    h, w = dmap.shape
    scale = max(w, h) / 1280
    zmin = min(zs.values()) - 100
    zmax = max(zs.values()) + 300
    norm = np.clip((dmap - zmin) / (zmax - zmin), 0, 1)
    norm = np.nan_to_num(norm, nan=1.0)
    img = cv2.applyColorMap((255 * (1 - norm)).astype(np.uint8), cv2.COLORMAP_TURBO)
    draw_points(img, pts, zs, scale)
    put_text(img, f"depth color: red {zmin:.0f}mm - blue {zmax:.0f}mm", (12, round(30 * scale)), 0.7 * scale)
    return img


if __name__ == "__main__":
    sys.exit(main())
