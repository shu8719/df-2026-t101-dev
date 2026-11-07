r"""写真1枚で、Depth Anything 3 の組み合わせを試す（docs/depth-scale-da3/scripts.md §5）。

組み合わせ（docs/depth-scale-da3/method.md §3）：
  da3+depthpro   DA3METRIC ＋ Depth Pro の焦点距離（研究目的の物差しとしてだけ使う）
  da3+moge2vits  DA3METRIC ＋ MoGe-2（小さい版）の焦点距離（本命）
  da3+moge2vitl  DA3METRIC ＋ MoGe-2（大きい版）の焦点距離（本命）
  moge2vitl*da3  MoGe-2 の形を、DA3 の深度（焦点距離は MoGe-2）で伸び縮み（vits も可）
  da3+da3base    DA3METRIC ＋ DA3-BASE の焦点距離
Depth Pro・MoGe-2 の結果は、それぞれの try_image が保存した JSON を読む（先に動かしておく）。

使い方：.venv\Scripts\python try_image_da3.py <写真> [--combos ...] [--truth 0→5,0→9,0→17,5→17]
注意：写真はどこにも保存しない。結果の画像と数値だけを data/vis/ に保存する（コミットしない）。
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import cv2
import numpy as np

import da3_backend as db
from da3_backend import dp
import focal_sources as fs
import landmarks as dp_landmarks  # Depth Pro 側の MediaPipe の呼び方
import try_image as dp_try        # Depth Pro 側の画像の描き方

DEFAULT_COMBOS = "da3+depthpro,da3+moge2vits,da3+moge2vitl,moge2vitl*da3,da3+da3base"
SEG_SHORT = {"seg_0_5_mm": "0→5", "seg_0_9_mm": "0→9", "seg_0_17_mm": "0→17", "seg_5_17_mm": "5→17"}


def depth_at_points(depth_mm: np.ndarray, pts: list, radius: float) -> dict[int, float]:
    zs = {}
    for p in dp.DEPTH_POINTS:
        z = dp.patch_depth(dp.extract_patch(depth_mm, *pts[p]), radius)
        if z is None:
            raise SystemExit(f"点 {p} の深度が出ませんでした")
        zs[p] = z
    return zs


def lengths_from_depth(zs: dict[int, float], pts: list, f_px: float, w: int, h: int, offset: float) -> dict[str, float]:
    xyz = {p: dp.backproject(*pts[p], z + offset, f_px, w / 2, h / 2) for p, z in zs.items()}
    return {k: float(np.linalg.norm(xyz[a] - xyz[b])) for k, (a, b) in dp.SEGMENTS.items()}


def run_combo(combo: str, rgb, pts, stem, metric, base, radius, offset) -> dict:
    h, w = rgb.shape[:2]
    if combo.startswith("da3+"):
        src = combo[4:]
        if src == "da3base":
            f, t_f = base.focal(rgb)
        else:
            f, t_f = fs.image_focal(src, stem, (w, h)), 0.0
        r = metric.metric(rgb, f)
        zs = depth_at_points(r.depth_mm, pts, radius)
        return {"combo": combo, "f_px": f, "z_mm": {p: z + offset for p, z in zs.items()},
                "lengths_mm": lengths_from_depth(zs, pts, f, w, h, offset), "infer_s": r.infer_s + t_f,
                "proc_wh": r.proc_wh, "depth_mm": r.depth_mm}
    if "*da3" in combo:  # 形は MoGe-2、倍率は DA3（焦点距離は MoGe-2）
        src = combo.split("*")[0]
        mg = fs.load_image_result(src, stem)
        f = fs.image_focal(src, stem, (w, h))
        r = metric.metric(rgb, f)
        z_da3 = depth_at_points(r.depth_mm, pts, radius)
        ratios = [(z_da3[p] + offset) / float(mg["z_mm"][str(p)]) for p in dp.DEPTH_POINTS]
        s = float(np.median(ratios))
        return {"combo": combo, "f_px": f, "scale": s,
                "z_mm": {p: s * float(mg["z_mm"][str(p)]) for p in dp.DEPTH_POINTS},
                "lengths_mm": {k: s * float(v) for k, v in mg["lengths_mm"].items()}, "infer_s": r.infer_s,
                "proc_wh": r.proc_wh, "depth_mm": r.depth_mm}
    raise SystemExit(f"知らない組み合わせです：{combo}")


def refs(stem: str) -> dict[str, dict]:
    """並べるための、Depth Pro・MoGe-2 単独の結果（あれば）"""
    out = {}
    for name, src in (("Depth Pro", "depthpro"), ("MoGe-2（vitl）", "moge2vitl"), ("MoGe-2（vits）", "moge2vits")):
        p = fs.image_json(src, stem)
        if p.exists():
            out[name] = dp.load_json(p)
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", type=Path)
    ap.add_argument("--combos", default=DEFAULT_COMBOS)
    ap.add_argument("--truth", help="正解（mm）を 0→5,0→9,0→17,5→17 の順にカンマ区切りで")
    ap.add_argument("--radius", type=float, default=3.0)
    ap.add_argument("--skin-offset-mm", type=float, default=0.0)
    ap.add_argument("--max-long-side", type=int, default=1280)
    ap.add_argument("--landmarker", type=Path, default=dp_landmarks.DEFAULT_MODEL)
    ap.add_argument("--constant", action="store_true", help="重みなしで流れだけを確かめる偽物を使う")
    ap.add_argument("--no-save", action="store_true")
    a = ap.parse_args(argv)
    combos = [c.strip() for c in a.combos.split(",") if c.strip()]
    truth = None
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
    h, w = bgr.shape[:2]
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    stem = a.image.stem

    mp, lmk = dp_landmarks.create_landmarker(a.landmarker)
    used, reason, pts = dp_landmarks.judge(lmk.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)).hand_landmarks, w, h)
    if pts is None:
        raise SystemExit(f"手の21点が取れませんでした（{reason}）")
    if not used:
        print(f"注意：{reason}（手が画面の端にかかっている）。結果は参考程度に")

    print("Depth Anything 3 を読み込んでいます（初回は重みを取ってくるので時間がかかります）…")
    if a.constant:
        metric = base = db.ConstantBackend()
    else:
        metric = db.DA3Backend("metric")
        base = db.DA3Backend("base") if any(c == "da3+da3base" for c in combos) else None
    results = [run_combo(c, rgb, pts, stem, metric, base, a.radius, a.skin_offset_mm) for c in combos]
    others = refs(stem)

    # ---------- 表示 ----------
    print()
    print(f"画像：{w}×{h}px　DA3 が見た大きさ：{results[0]['proc_wh'][0]}×{results[0]['proc_wh'][1]}px　（{metric.device_name()}）")
    cols = [(n, o) for n, o in others.items()] + [(r["combo"], r) for r in results]
    head = "| 項目 | " + ("正解 | " if truth else "") + " | ".join(n for n, _ in cols) + " |"
    print(head)
    print("|---" * (len(cols) + 1 + (1 if truth else 0)) + "|")
    for k in dp.SEGMENTS:
        cells = []
        for _, o in cols:
            L = float(o["lengths_mm"][k])
            cells.append(f"{L:.1f}" + (f"（{(L / truth[k] - 1) * 100:+.1f}%）" if truth else ""))
        print(f"| {SEG_SHORT[k]}（mm） | " + (f"{truth[k]:.1f} | " if truth else "") + " | ".join(cells) + " |")
    print("| 手首まで（mm） | " + ("— | " if truth else "") + " | ".join(f"{float(o['z_mm']['0'] if '0' in o['z_mm'] else o['z_mm'][0]):.0f}" for _, o in cols) + " |")
    print("| 焦点距離（px） | " + ("— | " if truth else "") + " | ".join(f"{float(o['f_px']):.0f}" for _, o in cols) + " |")
    print("| 時間（秒） | " + ("— | " if truth else "") + " | ".join(f"{float(o.get('infer_s', math.nan)):.2f}" for _, o in cols) + " |")
    if truth:
        print()
        print("ずれ（4区間の「長さ ÷ 正解」の中央値。合格の目安は ±2% 以内）")
        for n, o in cols:
            ratio = dp.scale_ratio({k: float(v) for k, v in o["lengths_mm"].items()}, truth)
            print(f"  {n}：{dp.deviation_pct(ratio):+.1f}%")
    for r in results:
        if "scale" in r:
            print(f"（{r['combo']} の倍率：{r['scale']:.3f}）")

    # ---------- 保存 ----------
    if not a.no_save:
        out_dir = db.DATA / "vis"
        out_dir.mkdir(parents=True, exist_ok=True)
        tiles = []
        for r in results:
            zs = {int(p): float(z) for p, z in r["z_mm"].items()}
            ov = dp_try.draw_overlay(bgr, pts, zs, r["lengths_mm"], r["f_px"])
            dp_try.put_text(ov, r["combo"], (12, h - 20), 0.9 * max(w, h) / 1280, (0, 255, 255))
            dv = dp_try.draw_depth(r["depth_mm"], pts, zs)
            safe = r["combo"].replace("*", "x").replace("+", "_")
            cv2.imwrite(str(out_dir / f"{stem}_{safe}_side.jpg"), np.hstack([ov, dv]), [cv2.IMWRITE_JPEG_QUALITY, 90])
            tiles.append(ov)
        while len(tiles) % 3:
            tiles.append(np.zeros_like(tiles[0]))
        grid = np.vstack([np.hstack(tiles[i:i + 3]) for i in range(0, len(tiles), 3)])
        cv2.imwrite(str(out_dir / f"{stem}_da3_all.jpg"), grid, [cv2.IMWRITE_JPEG_QUALITY, 85])
        dp.save_json(out_dir / f"{stem}_da3.json", {
            "image": a.image.name, "width": w, "height": h, "radius_px": a.radius, "skin_offset_mm": a.skin_offset_mm,
            "truth_mm": truth, "results": [{k: (v if k != "z_mm" else {str(p): z for p, z in v.items()})
                                            for k, v in r.items() if k != "depth_mm"} for r in results]})
        print()
        print(f"画像と数値を保存しました（data/ の中なのでコミットされません）：{out_dir}")
        print(f"  全部の組み合わせを並べた画像：{out_dir / f'{stem}_da3_all.jpg'}")


if __name__ == "__main__":
    sys.exit(main())
