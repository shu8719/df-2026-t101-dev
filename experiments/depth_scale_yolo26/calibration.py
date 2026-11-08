"""全部の写真・全部のモデルの結果を集め、「ずれの平均で直す補正」を1枚を除く確かめで評価する
（docs/depth-scale-yolo26/method.md §4）。

出力（data/vis/ と data/results/、コミットしない）：summary.md・summary.csv・summary_scatter.png
正解は写真1の Depth Pro の値（本人が定規で確かめた値）。基準は定規の値で、Depth Pro の出力は本番の計算に使わない。
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

import yolo26_backend as yb
from yolo26_backend import EXP, dp

TRUTH = {"seg_0_5_mm": 75.5, "seg_0_9_mm": 72.3, "seg_0_17_mm": 69.3, "seg_5_17_mm": 61.8}
PALM = {"IMG_6509", "IMG_6510"}  # 手のひらを上にした写真（手首と付け根の点の取られ方が違う）
TRUTH_PHOTO = "9DCCF180-3527-47E8-8201-ECD3D4D540BA"  # 正解を決めた写真
PHOTO_DIR = EXP / "depth_scale" / "data"


def load(p: Path):
    return dp.load_json(p) if p.exists() else None


def collect() -> dict[str, dict[str, dict]]:
    """方法 → 写真 → 長さ"""
    out: dict[str, dict[str, dict]] = {}
    def put(method, stem, L):  # noqa: E306
        if L:
            out.setdefault(method, {})[stem] = {k: float(v) for k, v in L.items()}
    for ph in sorted(p for p in PHOTO_DIR.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png")):
        s = ph.stem
        r = load(EXP / "depth_scale" / "data" / "vis" / f"{s}_depthpro.json")
        put("Depth Pro（研究用）", s, r and r["lengths_mm"])
        r = load(EXP / "depth_scale_moge2" / "data" / "vis" / f"{s}_moge2_vitl.json")
        put("MoGe-2", s, r and r["lengths_mm"])
        r = load(EXP / "depth_scale_da3" / "data" / "vis" / f"{s}_da3.json")
        for c in (r or {}).get("results", []):
            name = {"da3+depthpro": "DA3（焦点距離 Depth Pro）", "da3+moge2vitl": "DA3（焦点距離 MoGe-2）"}.get(c["combo"])
            if name:
                put(name, s, c["lengths_mm"])
        r = load(EXP / "depth_scale_mapanything" / "data" / "vis" / f"{s}_mapanything.json")
        put("MapAnything", s, r and r["lengths_mm"])
        r = load(yb.DATA / "vis" / f"{s}_yolo26.json")
        for v in (r or {}).get("results", {}).values():
            put(f"YOLO26{v['size']}（{v['focal']}）", s, v["lengths_mm"])
    return out


def evaluate(per_photo: dict[str, dict], exclude: set[str]) -> dict:
    """写真ごとの比と、1枚を除く補正後のずれ"""
    ratios = {s: dp.scale_ratio(L, TRUTH) for s, L in per_photo.items() if s not in exclude}
    ratios = {s: r for s, r in ratios.items() if math.isfinite(r)}
    if len(ratios) < 2:
        return {}
    raw = {s: (r - 1) * 100 for s, r in ratios.items()}
    corr = {}
    for s, r in ratios.items():
        others = [x for t, x in ratios.items() if t != s]
        corr[s] = (r / (sum(others) / len(others)) - 1) * 100
    mean_ratio = sum(ratios.values()) / len(ratios)
    a = lambda d: [abs(v) for v in d.values()]  # noqa: E731
    return {"n": len(ratios), "raw": raw, "corr": corr, "factor": 1 / mean_ratio,
            "raw_med": float(np.median(a(raw))), "raw_max": max(a(raw)),
            "corr_med": float(np.median(a(corr))), "corr_max": max(a(corr)),
            "pass": float(np.median(a(corr))) <= 2.0 and max(a(corr)) <= 4.0}


def plot(results: dict[str, dict], path: Path, title: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = sorted(results, key=lambda n: results[n]["corr_med"])
    fig, axes = plt.subplots(1, 2, figsize=(14, 0.42 * len(names) + 1.8), dpi=110, sharey=True)
    for ax, key, sub in ((axes[0], "raw", "before correction"), (axes[1], "corr", "after correction (leave-one-out)")):
        for i, n in enumerate(names):
            vals = list(results[n][key].values())
            ax.scatter(vals, [i] * len(vals), s=22, alpha=0.75, color="#0072b2" if not results[n]["pass"] else "#009e73")
            ax.plot([float(np.median(vals))], [i], marker="|", markersize=16, color="black")
        ax.axvspan(-2, 2, color="#009e73", alpha=0.15)
        ax.axvline(0, color="black", lw=0.8)
        ax.set_title(sub)
        ax.set_xlabel("error vs truth (%)")
        ax.grid(alpha=0.3)
        if key == "raw":
            ax.set_xlim(-60, max(160, max(max(results[n]["raw"].values()) for n in names) * 0.0 + 160))
        else:
            ax.set_xlim(-40, 40)
    axes[0].set_yticks(range(len(names)))
    axes[0].set_yticklabels([n.replace("（", " (").replace("）", ")").replace("研究用", "research only")
                             .replace("焦点距離 ", "f ") for n in names], fontsize=8)
    fig.suptitle(title + "  (green band = +-2%, green dots = pass)")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def table(results: dict[str, dict]) -> list[str]:
    lines = ["| 方法 | 枚数 | 補正前：ずれの中央値 | 補正前：最大 | 補正値（掛ける数） | 補正後：中央値 | 補正後：最大 | 判定 |",
             "|---|---|---|---|---|---|---|---|"]
    for n in sorted(results, key=lambda n: results[n]["corr_med"]):
        r = results[n]
        lines.append(f"| {n} | {r['n']} | {r['raw_med']:.1f}% | {r['raw_max']:.1f}% | ×{r['factor']:.3f} | "
                     f"{r['corr_med']:.1f}% | {r['corr_max']:.1f}% | {'**合格**' if r['pass'] else '不合格'} |")
    return lines


def main() -> None:
    data = collect()
    out_md = ["# 補正の評価（自動で作った表）", "",
              "ずれは「4区間の、長さ ÷ 正解」の中央値。補正は、1枚を除いた残りの写真の比の平均で割る（1枚を除く確かめ）。",
              "合格の目安：補正後のずれの絶対値の中央値 2% 以内・最大 4% 以内。Depth Pro は正解を決めた写真1を除いて評価する。", ""]
    for label, excl in (("手の甲の写真だけ（手のひらの写真を除く）", PALM), ("全部の写真", set())):
        res = {}
        for m, per in data.items():
            ex = set(excl) | ({TRUTH_PHOTO} if m.startswith("Depth Pro") else set())
            r = evaluate(per, ex)
            if r:
                res[m] = r
        out_md += [f"## {label}", ""] + table(res) + [""]
        tag = "back" if excl else "all"
        plot(res, yb.DATA / "vis" / f"summary_scatter_{tag}.png", "back of hand only" if excl else "all photos")
        if excl:
            stems = sorted({s for r in res.values() for s in r["raw"]})
            out_md += ["### 写真ごとの補正前のずれ（手の甲の写真）", "",
                       "| 方法 | " + " | ".join(s[:8] for s in stems) + " |", "|---" * (len(stems) + 1) + "|"]
            for n in sorted(res, key=lambda n: res[n]["corr_med"]):
                out_md.append(f"| {n} | " + " | ".join(f"{res[n]['raw'][s]:+.0f}%" if s in res[n]["raw"] else "" for s in stems) + " |")
            out_md.append("")
    p = yb.DATA / "results" / "summary.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(out_md) + "\n", encoding="utf-8")
    print("\n".join(out_md))
    print(f"\n表：{p}\nグラフ：{yb.DATA / 'vis' / 'summary_scatter_back.png'}")


if __name__ == "__main__":
    sys.exit(main())
