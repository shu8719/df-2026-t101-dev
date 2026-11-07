"""⑤ ノギス・1円玉・Depth Pro・MoGe-2 を1つの表に並べる（docs/depth-scale-moge2/scripts.md §5.2）。

ずれ・1人を除く補正・合否の計算は、Depth Pro 側の compare.py の関数を使う。
MoGe-2 は本命（source=points）の長さを使う。

使い方：python compare_all.py --radius 3 --skin-offset-mm 0
"""
from __future__ import annotations

import argparse
import math
import sys

import moge_backend as mb
from moge_backend import dp
import compare as dp_compare  # Depth Pro 側の比べ方

MODEL_LABEL = {"vitl": "MoGe-2（vitl）", "vits": "MoGe-2（vits）", "constant": "MoGe-2（偽物）"}


def _suffix(subset: str) -> str:
    return "" if subset == "all" else "（8枚）"


def _match(row: dict, radius: float, offset: float) -> bool:
    return (row.get("status") == "ok" and dp.to_float(row["radius_px"]) == radius
            and dp.to_float(row["skin_offset_mm"]) == offset)


def collect(radius: float, offset: float) -> list[dict]:
    recs = {r["rec_id"]: r for r in dp.recordings()}
    truth = {r["person"]: {k: dp.to_float(r[k]) for k in dp.SEGMENTS} for r in dp.read_csv(dp.DATA / "truth.csv")}
    dp_rows = dp.read_csv(dp.DATA / "results" / "lengths.csv") if (dp.DATA / "results" / "lengths.csv").exists() else []
    mg_path = mb.DATA / "results" / "lengths.csv"
    mg_rows = dp.read_csv(mg_path) if mg_path.exists() else []
    rows = []
    for rid, rec in recs.items():
        t = truth.get(rec["person"])
        if not t:
            print(f"{rid}: truth.csv に {rec['person']} の正解がないので飛ばします")
            continue
        base = {"rec_id": rid, "person": rec["person"]}
        c = dp_compare.coin_lengths(rid)
        if c:
            rows.append({**base, "method": "1円玉", "ratio": dp.scale_ratio(c, t), "time": None})
        for lr in dp_rows:
            if lr["rec_id"] == rid and _match(lr, radius, offset):
                L = {k: dp.to_float(lr[k]) for k in dp.SEGMENTS}
                rows.append({**base, "method": f"Depth Pro {lr['cond']}{_suffix(lr['subset'])}", "ratio": dp.scale_ratio(L, t),
                             "time": dp.DATA / "depth" / rid / f"{lr['cond']}.json"})
        for lr in mg_rows:
            if lr["rec_id"] == rid and lr["source"] == "points" and _match(lr, radius, offset):
                L = {k: dp.to_float(lr[k]) for k in dp.SEGMENTS}
                rows.append({**base, "method": f"{MODEL_LABEL.get(lr['model'], lr['model'])} {lr['cond']}{_suffix(lr['subset'])}",
                             "ratio": dp.scale_ratio(L, t), "time": mb.DATA / "points" / rid / f"{lr['model']}_{lr['cond']}.json"})
    return rows


def median_time(paths: list) -> float:
    xs = []
    for p in paths:
        if p is not None and p.exists():
            xs += [f["infer_s"] for f in dp.load_json(p)["frames"]]
    return dp.median(xs) if xs else math.nan


def order_key(m: str) -> tuple:
    head = 0 if m == "1円玉" else 1 if m.startswith("Depth Pro") else 2
    return (head, m)


def write_md(rows: list[dict], summary: list[dict], radius: float, offset: float) -> str:
    methods = sorted({r["method"] for r in rows}, key=order_key)
    fmt = lambda x: "" if x is None or not math.isfinite(x) else f"{x:+.1f}"  # noqa: E731
    lines = [f"条件：点のまわりの半径 {radius:g}px、深度に足した量 {offset:g}mm。ずれは「長さ ÷ ノギス」の4区間の中央値（%）", "",
             "### ずれ（%）", "", "| # | " + " | ".join(methods) + " |", "|---" * (len(methods) + 1) + "|"]
    for rid in sorted({r["rec_id"] for r in rows}):
        by = {r["method"]: r for r in rows if r["rec_id"] == rid}
        cells = [fmt(dp.deviation_pct(by[m]["ratio"])) if m in by else "" for m in methods]
        lines.append(f"| {rid} | " + " | ".join(cells) + " |")
    a = lambda x: "" if not math.isfinite(x) else f"{x:.1f}"  # noqa: E731
    lines += ["", "### まとめ", "",
              "| 条件 | 件数 | 中央値 | 最大 | 補正後の中央値 | 補正後の最大 | 同じ人のばらつき | 1枚あたりの時間（秒） | 合否 |",
              "|---|---|---|---|---|---|---|---|---|"]
    for s in sorted(summary, key=lambda s: order_key(s["method"])):
        t = "" if not math.isfinite(s["infer_s"]) else f"{s['infer_s']:.2f}"
        lines.append(f"| {s['method']} | {s['n']} | {a(s['median_abs_pct'])} | {a(s['max_abs_pct'])} | {a(s['corr_median_abs_pct'])} | "
                     f"{a(s['corr_max_abs_pct'])} | {a(s['spread_max_pct'])} | {t} | {s['pass']} |")
    lines += ["", f"合格の目安：ずれの絶対値の中央値 {dp_compare.PASS_MEDIAN_PCT}% 以内、最大 {dp_compare.PASS_MAX_PCT}% 以内、"
              f"同じ人のばらつき {dp_compare.PASS_SPREAD_PCT}% 以内（補正前の値で判定）"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--radius", type=float, default=3.0)
    ap.add_argument("--skin-offset-mm", type=float, default=0.0)
    a = ap.parse_args(argv)
    rows = collect(a.radius, a.skin_offset_mm)
    if not rows:
        raise SystemExit("比べるものがありません（truth.csv・coin/・両方の lengths.csv を確かめてください）")
    dp_compare.add_corrected(rows)
    summary = dp_compare.summarize(rows)
    for s in summary:  # 時間は、方法ごとの推論の記録から取り直す（Depth Pro 側の summarize は名前から探すため）
        s["infer_s"] = median_time([r["time"] for r in rows if r["method"] == s["method"]])
    res = mb.DATA / "results"
    dp.write_csv(res / "summary_all.csv", [
        {"rec_id": r["rec_id"], "person": r["person"], "method": r["method"],
         "deviation_pct": round(dp.deviation_pct(r["ratio"]), 3),
         "corrected_deviation_pct": round(dp.deviation_pct(r["corrected_ratio"]), 3) if math.isfinite(r["corrected_ratio"]) else ""}
        for r in rows], ["rec_id", "person", "method", "deviation_pct", "corrected_deviation_pct"])
    md = write_md(rows, summary, a.radius, a.skin_offset_mm)
    (res / "summary_all.md").write_text(md, encoding="utf-8")
    meta = dp_compare.meta(vars(a))
    meta["packages"]["moge"] = dp_compare.pkg("moge")
    dp.save_json(res / "meta.json", meta)
    print(md)


if __name__ == "__main__":
    sys.exit(main())
