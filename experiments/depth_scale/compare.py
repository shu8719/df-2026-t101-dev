"""⑤ ノギス・1円玉と比べて、表を作る（docs/depth-scale/scripts.md §7）。

撮影ごと・方法ごとに、4区間の「長さ ÷ ノギス」の中央値からずれ（%）を出す。
1人を除いて求めた補正係数での、補正後のずれも出す。
summary.md は docs/depth-scale/experiment.md §6.2・§6.3 にそのまま貼れる形にする。

使い方：python compare.py   （主に見る設定は --radius 3 --skin-offset-mm 0）
"""
from __future__ import annotations

import argparse
import math
import platform
import subprocess
import sys
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version

import common

# 1円玉の採寸 JSON（measurement.md §12）の項目 → 区間
COIN_KEYS = {
    "seg_0_5_mm": "wrist_to_index_mcp_mm",
    "seg_0_9_mm": "wrist_to_middle_mcp_mm",
    "seg_0_17_mm": "wrist_to_pinky_mcp_mm",
    "seg_5_17_mm": "hand_width_mcp_mm",
}
# 合格の目安（experiment.md §5）
PASS_MEDIAN_PCT = 2.0
PASS_MAX_PCT = 4.0
PASS_SPREAD_PCT = 2.0


def coin_lengths(rec_id: str) -> dict[str, float] | None:
    p = common.DATA / "coin" / f"{rec_id}.json"
    if not p.exists():
        return None
    m = common.load_json(p)
    palm = m.get("palm", {})
    if palm.get("segments_source") == "manual":
        print(f"{rec_id}: 1円玉の採寸は点を直したあとのものなので使いません（scripts.md §2.3）")
        return None
    return {k: float(palm[v]) for k, v in COIN_KEYS.items() if v in palm}


def method_name(row: dict) -> str:
    return row["cond"] if row["subset"] == "all" else f"{row['cond']}（8枚）"


def collect(radius: float, offset: float) -> tuple[list[dict], dict[str, str]]:
    """撮影 × 方法 ごとの比。戻り値は（行の一覧、撮影ID → 人）"""
    recs = {r["rec_id"]: r for r in common.recordings()}
    truth = {r["person"]: {k: common.to_float(r[k]) for k in common.SEGMENTS} for r in common.read_csv(common.DATA / "truth.csv")}
    lengths_path = common.DATA / "results" / "lengths.csv"
    lrows = common.read_csv(lengths_path) if lengths_path.exists() else []
    rows = []
    for rid, rec in recs.items():
        t = truth.get(rec["person"])
        if not t:
            print(f"{rid}: truth.csv に {rec['person']} の正解がないので飛ばします")
            continue
        c = coin_lengths(rid)
        if c:
            rows.append({"rec_id": rid, "person": rec["person"], "method": "1円玉", "ratio": common.scale_ratio(c, t)})
        for lr in lrows:
            if lr["rec_id"] != rid or lr["status"] != "ok":
                continue
            if common.to_float(lr["radius_px"]) != radius or common.to_float(lr["skin_offset_mm"]) != offset:
                continue
            L = {k: common.to_float(lr[k]) for k in common.SEGMENTS}
            rows.append({"rec_id": rid, "person": rec["person"], "method": method_name(lr),
                         "ratio": common.scale_ratio(L, t), "f_px_median": common.to_float(lr["f_px_median"])})
    return rows, {rid: r["person"] for rid, r in recs.items()}


def add_corrected(rows: list[dict]) -> None:
    for m in {r["method"] for r in rows}:
        mine = [r for r in rows if r["method"] == m]
        by_p: dict[str, list[dict]] = {}
        for r in mine:
            by_p.setdefault(r["person"], []).append(r)
        corr = common.loo_corrected({p: [r["ratio"] for r in rs] for p, rs in by_p.items()})
        for p, rs in by_p.items():
            for r, c in zip(rs, corr[p]):
                r["corrected_ratio"] = c
        allr = [r["ratio"] for r in mine if math.isfinite(r["ratio"])]
        for r in mine:
            r["factor_all"] = 1.0 / (sum(allr) / len(allr)) if allr else math.nan


def infer_seconds(rec_id: str, cond: str) -> float:
    p = common.DATA / "depth" / rec_id / f"{cond}.json"
    if not p.exists():
        return math.nan
    return common.median(f["infer_s"] for f in common.load_json(p)["frames"])


def device_focal_diff_pct(rec_id: str, f_model: float) -> float:
    """条件Aで推定した焦点距離と、機種の値から出した焦点距離の差（%）"""
    rec = next((r for r in common.recordings() if r["rec_id"] == rec_id), {})
    fj = common.DATA / "frames" / rec_id / "frames.json"
    f35 = common.to_float(rec.get("focal_35mm_mm"))
    if not fj.exists() or not math.isfinite(f35) or not math.isfinite(f_model):
        return math.nan
    fr = common.load_json(fj)["frames"][0]
    f_dev = common.f_px_from_35mm(f35, fr["width"], fr["height"])
    return (f_model / f_dev - 1.0) * 100.0


def fmt(x: float, nd: int = 1) -> str:
    return "" if x is None or not math.isfinite(x) else f"{x:+.{nd}f}"


def summarize(rows: list[dict]) -> list[dict]:
    out = []
    order = ["1円玉", "A", "B", "B（8枚）", "C"]
    for m in sorted({r["method"] for r in rows}, key=lambda m: order.index(m) if m in order else 99):
        mine = [r for r in rows if r["method"] == m]
        dev = [abs(common.deviation_pct(r["ratio"])) for r in mine if math.isfinite(r["ratio"])]
        cdev = [abs(common.deviation_pct(r["corrected_ratio"])) for r in mine if math.isfinite(r.get("corrected_ratio", math.nan))]
        spreads = []
        for p in {r["person"] for r in mine}:
            ds = [common.deviation_pct(r["ratio"]) for r in mine if r["person"] == p and math.isfinite(r["ratio"])]
            if len(ds) >= 2:
                spreads.append(max(ds) - min(ds))
        cond = m[0] if m != "1円玉" else None
        secs = [infer_seconds(r["rec_id"], cond) for r in mine] if cond else []
        med, mx = common.median(dev), max(dev) if dev else math.nan
        sp = max(spreads) if spreads else math.nan
        ok = math.isfinite(med) and med <= PASS_MEDIAN_PCT and mx <= PASS_MAX_PCT and (not math.isfinite(sp) or sp <= PASS_SPREAD_PCT)
        out.append({"method": m, "n": len(dev), "median_abs_pct": med, "max_abs_pct": mx,
                    "corr_median_abs_pct": common.median(cdev), "corr_max_abs_pct": max(cdev) if cdev else math.nan,
                    "spread_max_pct": sp, "infer_s": common.median(secs) if secs else math.nan,
                    "pass": "合格" if ok else "不合格", "factor_all": mine[0].get("factor_all", math.nan) if mine else math.nan})
    return out


def write_md(rows: list[dict], summary: list[dict], radius: float, offset: float) -> str:
    lines = [f"条件：点のまわりの半径 {radius:g}px、深度に足した量 {offset:g}mm。ずれは「長さ ÷ ノギス」の4区間の中央値（%）", "",
             "### 6.2 ずれ（%）", "",
             "| # | 1円玉 | A 全体・焦点距離もAI | B 切り抜き | B（8枚） | C 焦点距離を与える | Aの推定した焦点距離と機種の値の差（%） |",
             "|---|---|---|---|---|---|---|"]
    for rid in sorted({r["rec_id"] for r in rows}):
        by = {r["method"]: r for r in rows if r["rec_id"] == rid}
        cell = lambda m: fmt(common.deviation_pct(by[m]["ratio"])) if m in by else ""  # noqa: E731
        fdiff = device_focal_diff_pct(rid, by["A"]["f_px_median"]) if "A" in by else math.nan
        lines.append(f"| {rid} | {cell('1円玉')} | {cell('A')} | {cell('B')} | {cell('B（8枚）')} | {cell('C')} | {fmt(fdiff)} |")
    lines += ["", "### 6.3 まとめ", "",
              "| 条件 | 件数 | 中央値 | 最大 | 補正後の中央値 | 補正後の最大 | 同じ人の3回のばらつき | 1回あたりの時間（秒） | 合否 |",
              "|---|---|---|---|---|---|---|---|---|"]
    a = lambda x: "" if not math.isfinite(x) else f"{x:.1f}"  # noqa: E731
    for s in summary:
        t = "" if not math.isfinite(s["infer_s"]) else f"{s['infer_s']:.2f}"
        lines.append(f"| {s['method']} | {s['n']} | {a(s['median_abs_pct'])} | {a(s['max_abs_pct'])} | {a(s['corr_median_abs_pct'])} | "
                     f"{a(s['corr_max_abs_pct'])} | {a(s['spread_max_pct'])} | {t} | {s['pass']} |")
    lines += ["", f"合格の目安：ずれの絶対値の中央値 {PASS_MEDIAN_PCT}% 以内、最大 {PASS_MAX_PCT}% 以内、"
              f"同じ人のばらつき {PASS_SPREAD_PCT}% 以内（補正前の値で判定）。中央値・最大・ばらつきは絶対値（%）"]
    return "\n".join(lines) + "\n"


def pkg(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return ""


def meta(args: dict) -> dict:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=common.REPO, capture_output=True, text=True).stdout.strip()
    except OSError:
        commit = ""
    gpu = ""
    try:
        import torch
        gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    except ImportError:
        pass
    return {"run_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "commit": commit,
            "python": platform.python_version(), "gpu": gpu, "args": args,
            "packages": {n: pkg(n) for n in ("numpy", "opencv-python", "mediapipe", "torch", "depth_pro")}}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--radius", type=float, default=3.0)
    ap.add_argument("--skin-offset-mm", type=float, default=0.0)
    a = ap.parse_args(argv)
    rows, _ = collect(a.radius, a.skin_offset_mm)
    if not rows:
        raise SystemExit("比べるものがありません（truth.csv・coin/・results/lengths.csv を確かめてください）")
    add_corrected(rows)
    summary = summarize(rows)
    res = common.DATA / "results"
    common.write_csv(res / "summary.csv", [
        {"rec_id": r["rec_id"], "person": r["person"], "method": r["method"],
         "deviation_pct": round(common.deviation_pct(r["ratio"]), 3),
         "corrected_deviation_pct": round(common.deviation_pct(r["corrected_ratio"]), 3) if math.isfinite(r["corrected_ratio"]) else "",
         "factor_all": round(r["factor_all"], 4) if math.isfinite(r["factor_all"]) else ""} for r in rows],
        ["rec_id", "person", "method", "deviation_pct", "corrected_deviation_pct", "factor_all"])
    md = write_md(rows, summary, a.radius, a.skin_offset_mm)
    (res / "summary.md").write_text(md, encoding="utf-8")
    common.save_json(res / "meta.json", meta(vars(a)))
    print(md)


if __name__ == "__main__":
    sys.exit(main())
