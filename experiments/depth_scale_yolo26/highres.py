r"""解像度の効き目を確かめる：Depth Pro のように「細かい画像で見る」と、ほかのモデルの精度が上がるか。

- Depth Anything 3（METRIC）：見る画像の長い辺 504（既定）・756・1008・1512px
- YOLO26 Depth（m・l・x）：768（既定）・1024・1280px
12枚の写真で長さを出し、補正前・補正後（1枚を除く確かめ）のずれを比べる。焦点距離は「26mm の決め打ち」（本番で使える）。

使い方：..\depth_scale\.venv\Scripts\python highres.py
出力：data/results/highres.md・highres.json、data/vis/highres_scatter.png（コミットしない）
"""
from __future__ import annotations

import sys
import time

import cv2
import numpy as np

import calibration as cal
import focal as fc
import yolo26_backend as yb
from yolo26_backend import EXP, dp

sys.path.insert(0, str(EXP / "depth_scale_da3"))
import landmarks as dp_landmarks  # noqa: E402
import try_image_yolo26 as ty  # noqa: E402

DA3_RES = (504, 756, 1008, 1512)
YOLO_SIZES = ("m", "l", "x")
YOLO_RES = (768, 1024, 1280)


def load_photo(path):
    bgr = cv2.imread(str(path))
    s = min(1.0, 1280 / max(bgr.shape[:2]))
    if s < 1.0:
        bgr = cv2.resize(bgr, (round(bgr.shape[1] * s), round(bgr.shape[0] * s)), interpolation=cv2.INTER_AREA)
    return bgr


def main() -> None:
    photos = sorted(p for p in cal.PHOTO_DIR.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    mp, lmk = dp_landmarks.create_landmarker(dp_landmarks.DEFAULT_MODEL)
    items = []
    for ph in photos:
        bgr = load_photo(ph)
        H, W = bgr.shape[:2]
        _, _, pts = dp_landmarks.judge(lmk.detect(mp.Image(image_format=mp.ImageFormat.SRGB,
                                                           data=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))).hand_landmarks, W, H)
        if pts is None:
            print(f"{ph.name}：手の点が取れないので飛ばす")
            continue
        items.append((ph, bgr, pts, fc.focal("fixed26", ph, (W, H))))

    lengths: dict[str, dict[str, dict]] = {}
    times: dict[str, list[float]] = {}
    total = len(DA3_RES) * len(items) + len(YOLO_SIZES) * len(YOLO_RES) * len(items)
    done, t0 = 0, time.time()

    def tick(label):  # noqa: E306
        nonlocal done
        done += 1
        n = round(30 * done / total)
        el = time.time() - t0
        print(f"[{'#' * n}{'-' * (30 - n)}] {done}/{total}  経過 {el / 60:.1f}分  残り約 {el / done * (total - done) / 60:.1f}分  {label}", flush=True)

    import da3_backend as db
    da3 = db.DA3Backend("metric")
    for res in DA3_RES:
        name = f"DA3 {res}px"
        for ph, bgr, pts, f in items:
            r = da3.metric(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), f, process_res=res)
            L, _ = ty.lengths(r.depth_mm, pts, f)
            lengths.setdefault(name, {})[ph.stem] = L
            times.setdefault(name, []).append(r.infer_s)
            tick(f"{name} {ph.name}")
    del da3
    for size in YOLO_SIZES:
        model = yb.Yolo26Depth(size)
        for res in YOLO_RES:
            name = f"YOLO26{size} {res}px"
            for ph, bgr, pts, f in items:
                d, t = model.depth_mm(bgr, imgsz=res)
                L, _ = ty.lengths(d, pts, f)
                lengths.setdefault(name, {})[ph.stem] = L
                times.setdefault(name, []).append(t)
                tick(f"{name} {ph.name}")

    out = ["# 解像度の効き目（自動で作った表）", "",
           "焦点距離は 26mm の決め打ち。ずれは「4区間の、長さ ÷ 正解」の中央値。補正は1枚を除く確かめ。", ""]
    res_all = {}
    for label, excl in (("手の甲の写真だけ", cal.PALM), ("全部の写真", set())):
        res = {n: cal.evaluate(per, set(excl)) for n, per in lengths.items()}
        res = {n: r for n, r in res.items() if r}
        res_all[label] = res
        out += [f"## {label}", "",
                "| 方法 | 枚数 | 補正前：中央値 | 補正前：最大 | 補正値 | 補正後：中央値 | 補正後：最大 | 1枚の時間 | 判定 |",
                "|---|---|---|---|---|---|---|---|---|"]
        for n in lengths:
            if n not in res:
                continue
            r = res[n]
            out.append(f"| {n} | {r['n']} | {r['raw_med']:.1f}% | {r['raw_max']:.1f}% | ×{r['factor']:.3f} | "
                       f"{r['corr_med']:.1f}% | {r['corr_max']:.1f}% | {np.median(times[n]):.2f}秒 | {'**合格**' if r['pass'] else '不合格'} |")
        out.append("")
    p = yb.DATA / "results" / "highres.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(out) + "\n", encoding="utf-8")
    dp.save_json(yb.DATA / "results" / "highres.json", {"lengths": lengths, "times": times})
    cal.plot(res_all["手の甲の写真だけ"], yb.DATA / "vis" / "highres_scatter.png", "resolution test, back of hand only")
    print("\n".join(out))
    print(f"\n表：{p}\nグラフ：{yb.DATA / 'vis' / 'highres_scatter.png'}")


if __name__ == "__main__":
    sys.exit(main())
