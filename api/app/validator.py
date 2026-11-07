"""範囲チェック（docs/generation-pipeline.md §4 の R2〜R5 の一部。プロトタイプ版）。"""
from __future__ import annotations

import json
from pathlib import Path

from . import handmodel as hm

CATALOG = json.loads((Path(__file__).resolve().parents[2] / "scad" / "catalog.json").read_text(encoding="utf-8"))
C = CATALOG["constants"]


def clamp_ranges(params: dict, variant: str) -> tuple[dict, list[dict]]:
    """R2：範囲の端に丸め、丸めたものを記録する。"""
    clamped = []
    out = {part: dict(vals) for part, vals in params.items()}
    for part, vals in out.items():
        spec = CATALOG["parts"].get(part, {}).get("params", {})
        for name, v in list(vals.items()):
            s = spec.get(name)
            if s is None or not isinstance(v, (int, float)) or isinstance(v, bool):
                continue
            if "variants" in s and part == "grip_body" and variant not in s["variants"]:
                continue
            nv = min(max(v, s["min"]), s["max"])
            if nv != v:
                vals[name] = nv
                clamped.append({"part_id": part, "name": name, "from": v, "to": nv})
    return out, clamped


def check(params: dict, variant: str, tool_d_max: float) -> dict:
    """R4・R5（組み合わせと安全）。違反の一覧を返す。"""
    g = params["grip_body"]
    v = []
    bore_d = tool_d_max + 0.5
    if g.get("edge_radius_mm", 2.5) < C["MIN_EDGE_RADIUS_MM"]:
        v.append("EDGE_TOO_SHARP")
    if abs(g["d_top_mm"] - g["d_bottom_mm"]) > 15:
        v.append("TAPER_TOO_STEEP")
    if g["length_mm"] + C["THREAD_LENGTH_MM"] + C["COLLET_LENGTH_MM"] + 5 > C["BED_MM"][2]:
        v.append("TOO_TALL_FOR_BED")
    carve = None
    if variant == "fitted":
        carve = hm.carve_report(g["capsules"], g["d_bottom_mm"], g["d_top_mm"], g["length_mm"], bore_d,
                                C["CAPSULE_CLEARANCE_MM"], C["MAX_CARVE_RATIO"], C["MIN_WALL_AROUND_BORE_MM"])
        v += carve["problems"]
    else:
        ov = g.get("ovality", 1.0) if variant == "oval" else 1.0
        wall = (min(g["d_top_mm"], g["d_bottom_mm"]) * ov - 2 * g["groove_depth_mm"] - bore_d) / 2
        if wall < C["MIN_WALL_AROUND_BORE_MM"]:
            v.append("WALL_TOO_THIN")
        if g["groove_depth_mm"] > 0.2 * g["groove_width_mm"]:
            v.append("GROOVE_TOO_DEEP")
    return {"ok": not v, "violations": v, "carve": carve}
