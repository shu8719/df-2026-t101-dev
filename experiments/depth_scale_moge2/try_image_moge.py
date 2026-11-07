r"""写真1枚で、MoGe-2 の距離推定を試す（docs/depth-scale-moge2/scripts.md §6）。

Depth Pro 側の try_image.py と同じ使い方・同じ表示・同じ画像。長さは点群から出し（本命）、
深度と焦点距離から出した長さ（確かめ）も並べる。--compare-depth-pro を付けると、同じ写真の Depth Pro の結果
（experiments/depth_scale/data/vis/<写真の名前>_depthpro.json）があれば、数値を並べる。

使い方：.venv\Scripts\python try_image_moge.py <写真のパス> [--model vitl|vits] [--compare-depth-pro]
注意：写真はどこにも保存しない。結果の画像と数値だけを data/vis/ に保存する（コミットしない）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

import moge_backend as mb
from moge_backend import dp
import landmarks as dp_landmarks  # Depth Pro 側の MediaPipe の呼び方
import try_image as dp_try        # Depth Pro 側の画像の描き方

NAMES = dp_try.NAMES


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", type=Path)
    ap.add_argument("--model", default="vitl", choices=["vitl", "vits", "constant"])
    ap.add_argument("--radius", type=float, default=3.0)
    ap.add_argument("--skin-offset-mm", type=float, default=0.0)
    ap.add_argument("--max-long-side", type=int, default=1280)
    ap.add_argument("--landmarker", type=Path, default=dp_landmarks.DEFAULT_MODEL)
    ap.add_argument("--compare-depth-pro", action="store_true")
    ap.add_argument("--no-save", action="store_true")
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

    mp, lmk = dp_landmarks.create_landmarker(a.landmarker)
    res = lmk.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
    used, reason, pts = dp_landmarks.judge(res.hand_landmarks, w, h)
    if pts is None:
        raise SystemExit(f"手の21点が取れませんでした（{reason}）")
    if not used:
        print(f"注意：{reason}（手が画面の端にかかっている）。点がずれやすいので、結果は参考程度に")

    print(f"MoGe-2（{a.model}）を読み込んでいます（初回は重みを取ってくるので時間がかかります）…")
    backend = mb.make_backend(a.model)
    r = backend.infer(rgb)

    # 本命：点群から（カメラから点への距離も出す）
    xyz, zs = {}, {}
    for p in dp.DEPTH_POINTS:
        q = mb.patch_point(mb.extract_patch3(r.points_mm, *pts[p]), dp.extract_patch(r.mask.astype(np.float32), *pts[p]), a.radius)
        if q is None:
            raise SystemExit(f"点 {p} の3D位置が出ませんでした")
        xyz[p] = mb.push_out(q, a.skin_offset_mm)
        zs[p] = float(xyz[p][2])
    lengths = {k: float(np.linalg.norm(xyz[pa] - xyz[pb])) for k, (pa, pb) in dp.SEGMENTS.items()}
    # 確かめ：深度と焦点距離から
    xyz_d = {}
    for p in dp.DEPTH_POINTS:
        d = dp.extract_patch(r.depth_mm, *pts[p])
        d[np.nan_to_num(dp.extract_patch(r.mask.astype(np.float32), *pts[p]), nan=0.0) <= 0.5] = np.nan
        xyz_d[p] = dp.backproject(*pts[p], dp.patch_depth(d, a.radius) + a.skin_offset_mm, r.f_px, w / 2, h / 2)
    lengths_d = {k: float(np.linalg.norm(xyz_d[pa] - xyz_d[pb])) for k, (pa, pb) in dp.SEGMENTS.items()}

    dpj = dp.DATA / "vis" / f"{a.image.stem}_depthpro.json"
    other = dp.load_json(dpj) if a.compare_depth_pro and dpj.exists() else None
    if a.compare_depth_pro and other is None:
        print(f"注意：Depth Pro の結果（{dpj}）がないので、並べません。Depth Pro 側で try_image.py を先に動かしてください")

    print()
    print(f"画像：{w}×{h}px　推論：{r.infer_s:.2f} 秒（{backend.device_name()}）")
    print(f"推定した焦点距離：{r.f_px:.0f}px（35mm換算でおよそ {r.f_px * 43.27 / (w ** 2 + h ** 2) ** 0.5:.0f}mm）"
          + (f"　Depth Pro：{other['f_px']:.0f}px" if other else ""))
    print(f"カメラから手首まで：{zs[0]:.0f}mm　中指の付け根まで：{zs[9]:.0f}mm"
          + (f"　Depth Pro：{other['z_mm']['0']:.0f}mm・{other['z_mm']['9']:.0f}mm" if other else ""))
    print()
    print("手の甲の4区間" + ("（MoGe-2 ／ 確かめ：深度から ／ Depth Pro）" if other else "（MoGe-2 ／ 確かめ：深度から）"))
    for k in dp.SEGMENTS:
        line = f"  {NAMES[k]}：{lengths[k]:.1f}mm ／ {lengths_d[k]:.1f}mm"
        if other:
            line += f" ／ {other['lengths_mm'][k]:.1f}mm"
        print(line)
    worst = max(abs(lengths[k] / lengths_d[k] - 1) for k in dp.SEGMENTS) * 100
    print()
    print(f"点群と深度の長さの差：最大 {worst:.2f}%（0.5% を超えたら、焦点距離の直し方か単位の読み方を疑う）")

    if not a.no_save:
        out_dir = mb.DATA / "vis"
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{a.image.stem}_moge2_{a.model}"
        overlay = dp_try.draw_overlay(bgr, pts, zs, lengths, r.f_px)
        depth_vis = dp_try.draw_depth(np.where(np.isfinite(r.depth_mm), r.depth_mm, np.nan), pts, zs)
        mask_vis = mb.draw_mask(bgr, r.mask, pts)
        normal_vis = mb.draw_normal(r.normal, (h, w), pts)
        dp_try.put_text(mask_vis, "mask: red = not usable", (12, 30), 0.7 * max(w, h) / 1280)
        dp_try.put_text(normal_vis, "normal (x=R, y=G, z=B)", (12, 30), 0.7 * max(w, h) / 1280)
        images = {
            "overlay": overlay,                                   # 手の点・4区間の線と長さ・距離
            "depth": depth_vis,                                   # 深度（近い＝赤、遠い＝青）
            "mask": mask_vis,                                     # 使えない画素（赤）
            "normal": normal_vis,                                 # 面の向き
            "side": np.hstack([overlay, depth_vis]),              # 重ね描きと深度を横に並べたもの
            "grid": np.vstack([np.hstack([overlay, depth_vis]), np.hstack([mask_vis, normal_vis])]),  # 4枚まとめ
        }
        paths = {k: out_dir / f"{stem}_{k}.jpg" for k in images}
        for k, img in images.items():
            cv2.imwrite(str(paths[k]), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        dp.save_json(out_dir / f"{stem}.json", {
            "model": backend.name, "image": a.image.name, "width": w, "height": h, "f_px": r.f_px, "infer_s": r.infer_s,
            "radius_px": a.radius, "skin_offset_mm": a.skin_offset_mm, "z_mm": {str(p): z for p, z in zs.items()},
            "lengths_mm": lengths, "lengths_from_depth_mm": lengths_d})
        print()
        print("画像と数値を保存しました（data/ の中なのでコミットされません）：")
        for p in paths.values():
            print(f"  {p}")


if __name__ == "__main__":
    sys.exit(main())
