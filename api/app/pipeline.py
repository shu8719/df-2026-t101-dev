"""生成の流れ（docs/generation-pipeline.md）。プロトタイプ版：Geminiはモック、採寸はサンプルでもよい。"""
from __future__ import annotations

import copy
import os

from . import gemini_mock

if os.environ.get("GEMINI_MODE") == "live":
    from . import gemini_live as ai
else:
    ai = gemini_mock
from . import handmodel as hm
from . import scad_runner as scad
from . import store
from .validator import CATALOG, C, clamp_ranges, check

SIZE_TO_DIAMETER = {"thin": 7, "medium": 10, "thick": 13}
VIOLATION_JA = {
    "CARVE_TOO_DEEP": "指のくぼみが深くなりすぎて、サポートなしでは刷れない形です。太さを戻すか、くぼみを浅くしてください",
    "WALL_TOO_THIN": "柄を通す穴のまわりの壁が薄すぎます。握りを太くするか、くぼみを浅くしてください",
    "EDGE_TOO_SHARP": "角の丸みが小さすぎます",
    "TAPER_TOO_STEEP": "人差し指側と小指側の太さの差が大きすぎます",
    "TOO_TALL_FOR_BED": "プリンタで刷れる高さを超えています",
    "GROOVE_TOO_DEEP": "くぼみが幅に対して深すぎます",
}
DEFAULT_SIZE = {"brush": "medium", "pen": "medium", "spoon": "thick", "other": "medium"}


def tool_d_max(req: dict) -> float:
    d = req.get("tool_shaft_diameter_mm") or SIZE_TO_DIAMETER[DEFAULT_SIZE.get(req.get("tool_type", "brush"), "medium")]
    return round(d + 0.6, 1)


def baselines(case: dict) -> dict:
    """部品の基準値（parts-library.md §5）。fitted が作れるかも判定する。"""
    req, meas = case["requirements"], case["measurement"]
    model = hm.build(meas)
    td = tool_d_max(req)
    fitted = None
    if not any(model.cavities[f].diameter_mm is None for f in ("index", "pinky")):
        fitted = hm.baseline_fitted(model, td, C["CAPSULE_CLEARANCE_MM"])
        if fitted and fitted["press_depth_mm"] is None:
            fitted = None
    d_index = model.cavities["index"].diameter_mm or 32.0
    d_pinky = model.cavities["pinky"].diameter_mm or d_index
    mcp = meas["palm"]["mcp_positions_mm"]
    offsets = [mcp[f][0] - mcp["index"][0] for f in ("index", "middle", "ring", "pinky")]
    first = 14.0
    ring_params = {
        "length_mm": round(max(offsets[3] + 28, first + offsets[3] + 8 + 6), 1),
        "d_top_mm": round(min(max(d_index, 18), 55), 1), "d_bottom_mm": round(min(max(d_pinky, 18), 55), 1),
        "ovality": 0.85, "finger_pos_mm": [round(first + o, 1) for o in offsets],
        "groove_enabled": [True] * 4, "groove_width_mm": 16, "groove_depth_mm": 2.0,
    }
    common = {"bottom_flare_mm": 3, "edge_radius_mm": 2.5, "bore_through": True}
    return {"model": model, "tool_d_max": td, "fitted": fitted, "ring": ring_params, "common": common}


def _param_rows(params: dict, sources: dict) -> list[dict]:
    rows = []
    for part, vals in params.items():
        spec = CATALOG["parts"].get(part, {}).get("params", {})
        for name, v in vals.items():
            if name in ("capsules", "finger_pos_mm", "groove_enabled", "bore_through"):
                continue
            s = spec.get(name, {})
            rows.append({"part_id": part, "name": name, "label_ja": s.get("label_ja", name), "value": v,
                         "unit": s.get("unit", ""), "range": [s.get("min"), s.get("max")] if s else None,
                         "source": sources.get((part, name), "default")})
    return rows


def _scad_vars(params: dict, variant: str, nut_variant: str, hand: str, mode="assembled", quality="preview") -> dict:
    g, c, n = params["grip_body"], params["collet"], params["collet_nut"]
    v = {"hand": hand, "mode": mode, "quality": quality, "grip_body_variant": variant,
         "grip_body_length_mm": g["length_mm"], "grip_body_d_top_mm": g["d_top_mm"], "grip_body_d_bottom_mm": g["d_bottom_mm"],
         "grip_body_bottom_flare_mm": g["bottom_flare_mm"], "grip_body_edge_radius_mm": g["edge_radius_mm"],
         "grip_body_bore_through": g["bore_through"],
         "collet_tool_d_max_mm": c["tool_d_max_mm"], "collet_slot_count": c["slot_count"],
         "collet_nut_variant": nut_variant, "collet_nut_wing_span_mm": n["wing_span_mm"],
         "collet_nut_edge_radius_mm": n["edge_radius_mm"]}
    if variant == "fitted":
        v["grip_body_capsules"] = g["capsules"]
    else:
        v.update({"grip_body_ovality": g.get("ovality", 1.0), "grip_body_finger_pos_mm": g["finger_pos_mm"],
                  "grip_body_groove_enabled": g["groove_enabled"], "grip_body_groove_width_mm": g["groove_width_mm"],
                  "grip_body_groove_depth_mm": g["groove_depth_mm"]})
    return v


def _autofix(params: dict, variant: str, td: float, b: dict) -> tuple[dict, dict, list[str]]:
    """R4の自動の直し。直すたびに範囲と組み合わせを確かめ直す。"""
    notes = []
    for _ in range(12):
        params, clamped = clamp_ranges(params, variant)
        res = check(params, variant, td)
        if res["ok"]:
            return params, res, notes
        g = params["grip_body"]
        if variant == "fitted":
            if g["press_depth_mm"] > 0.5 and "CARVE_TOO_DEEP" in res["violations"]:
                g["press_depth_mm"] = round(g["press_depth_mm"] - 0.1, 1)
                d_i = b["model"].cavities["index"].diameter_mm
                d_p = b["model"].cavities["pinky"].diameter_mm
                g["d_top_mm"] = round(d_i + 2 * g["press_depth_mm"], 1)
                g["d_bottom_mm"] = round(d_p + 2 * g["press_depth_mm"], 1)
                notes.append("沿わせる深さを0.1mm浅くしました")
                continue
        else:
            if g["groove_depth_mm"] > 0.5:
                g["groove_depth_mm"] = round(g["groove_depth_mm"] - 0.5, 1)
                notes.append("くぼみを0.5mm浅くしました")
                continue
            if "WALL_TOO_THIN" in res["violations"]:
                g["d_top_mm"] = round(g["d_top_mm"] + 1, 1)
                g["d_bottom_mm"] = round(g["d_bottom_mm"] + 1, 1)
                notes.append("握りを1mm太くしました")
                continue
        break
    params, _ = clamp_ranges(params, variant)
    return params, check(params, variant, td), notes


# AIが変えてよい引数（parts-library.md §4 の「AIが変えてよい幅」。サーバーが決める capsules・length などは含めない）
AI_ADJUSTABLE = {("grip_body", "press_depth_mm"), ("grip_body", "edge_radius_mm"), ("grip_body", "bottom_flare_mm"),
                 ("grip_body", "ovality"), ("grip_body", "groove_width_mm"), ("grip_body", "groove_depth_mm"),
                 ("grip_body", "d_top_mm"), ("grip_body", "d_bottom_mm"),
                 ("collet", "slot_count"), ("collet_nut", "wing_span_mm"), ("collet_nut", "edge_radius_mm")}


def _apply_ai(params: dict, changes: list[dict], variant: str, b: dict, sources: dict) -> tuple[str | None, list[str]]:
    """AIの変更のうち、変えてよいものだけを当てる。fitted で沿わせる深さが変わったら太さも計算し直す。"""
    nut_variant, applied = None, []
    for ch in changes:
        part, name, val = ch.get("part_id"), ch.get("name"), ch.get("value")
        if part == "collet_nut" and name == "variant" and val in ("wings", "knurl"):
            nut_variant = val
            applied.append("ナットの種類")
            continue
        if (part, name) not in AI_ADJUSTABLE or not isinstance(val, (int, float)) or name not in params.get(part, {}):
            continue
        if variant == "fitted" and name in ("d_top_mm", "d_bottom_mm"):
            continue  # fitted の太さは、すき間＋沿わせる深さから決まる
        params[part][name] = round(float(val), 1) if name != "slot_count" else int(val)
        sources[(part, name)] = "ai"
        applied.append(name)
        if variant == "fitted" and name == "press_depth_mm":
            g = params["grip_body"]
            g["d_top_mm"] = round(b["model"].cavities["index"].diameter_mm + 2 * g["press_depth_mm"], 1)
            g["d_bottom_mm"] = round(b["model"].cavities["pinky"].diameter_mm + 2 * g["press_depth_mm"], 1)
    return nut_variant, applied


def _render_design(case: dict, design: dict) -> None:
    d = store.design_dir(case["case_id"], design["design_id"])
    variant = design["variant"]
    vars_ = _scad_vars(design["params"], variant, design["nut_variant"], case["requirements"]["hand_side"])
    stl = d / "preview.stl"
    scad.render_stl(vars_, stl)
    mc = scad.mesh_check(stl, 2)
    g = design["params"]["grip_body"]
    views = scad.render_views(stl, d / "views", {
        "color": design["style"]["color"], "tool_d": design["params"]["collet"]["tool_d_max_mm"] - 0.6,
        "tool_top_z": g["length_mm"] + C["THREAD_LENGTH_MM"] + C["COLLET_LENGTH_MM"] + 120,
        "hand": case["requirements"]["hand_side"], "capsules": g.get("capsules", []) if variant == "fitted" else []})
    design["files"] = {"preview_stl": store.rel(stl), "views": {k: store.rel(v) for k, v in views.items()}}
    design["mesh_check"] = mc


def create_design(case: dict, style: dict | None = None, parent: dict | None = None,
                  changes: list[dict] | None = None, origin: str = "initial") -> dict:
    b = baselines(case)
    req = case["requirements"]
    sel = ai.select(req, b["model"].warnings, b["fitted"] is not None)
    variant = sel["parts"][0]["variant"]
    nut_variant = sel["parts"][2]["variant"]
    td = b["tool_d_max"]
    sources = {}
    if parent is not None:
        params = copy.deepcopy(parent["params"])
        variant, nut_variant = parent["variant"], parent["nut_variant"]
        sources = {tuple(k.split("|")): v for k, v in parent.get("sources", {}).items()}
    elif variant == "fitted":
        f = b["fitted"]
        params = {"grip_body": {"press_depth_mm": f["press_depth_mm"], "end_margin_mm": f["end_margin_mm"],
                                "length_mm": f["length_mm"], "d_top_mm": f["d_top_mm"], "d_bottom_mm": f["d_bottom_mm"],
                                "capsules": f["capsules"], **b["common"]}}
        for n in ("length_mm", "d_top_mm", "d_bottom_mm", "capsules"):
            sources[("grip_body", n)] = "measured"
        sources[("grip_body", "press_depth_mm")] = "rule"
    else:
        params = {"grip_body": {**b["ring"], **b["common"]}}
        for n in ("length_mm", "d_top_mm", "d_bottom_mm"):
            sources[("grip_body", n)] = "measured"
    if parent is None:
        params["collet"] = {"tool_d_max_mm": td, "slot_count": 4 if req.get("tool_shaft_shape") == "flat" else 4}
        params["collet_nut"] = {"wing_span_mm": 50, "edge_radius_mm": 2.0}
        sources[("collet", "tool_d_max_mm")] = "interview"
    for ch in changes or []:
        if ch["part_id"] == "collet_nut" and ch["name"] == "variant":
            nut_variant = ch["value"]
            continue
        if ch["name"] in params.get(ch["part_id"], {}):
            params[ch["part_id"]][ch["name"]] = ch["value"]
            sources[(ch["part_id"], ch["name"])] = "ai" if origin == "refine_text" else "user"
    if origin == "initial":
        params, result, fix_notes = _autofix(params, variant, td, b)
    else:
        # ユーザーの指示（言葉・スライダー）は自動で打ち消さない。範囲だけ丸め、組み合わせの違反は知らせる
        params, _ = clamp_ranges(params, variant)
        result, fix_notes = check(params, variant, td), []
    if parent is None:
        # 寸法決め：AIが変えてよい引数だけを、範囲の中で調整する
        dim = ai.dimension(_param_rows(params, sources), req)
        nv, _ = _apply_ai(params, dim.get("params", []), variant, b, sources)
        nut_variant = nv or nut_variant
        params, result, more = _autofix(params, variant, td, b)
        fix_notes += more
    else:
        dim = {"params": [], "summary_ja": parent.get("summary_ja", "")}
    design = {
        "design_id": store.new_id("d"),
        "revision": len(case.get("designs", [])) + 1,
        "parent_design_id": parent["design_id"] if parent else None,
        "origin": origin, "status": "running", "progress": {"step": "rendering"},
        "variant": variant, "nut_variant": nut_variant,
        "parts": sel["parts"] if parent is None else parent["parts"],
        "params": params, "sources": {f"{k[0]}|{k[1]}": v for k, v in sources.items()},
        "validation": result, "autofix_notes": fix_notes,
        "style": style or (parent["style"] if parent else {"color": "#3A7CA5", "pattern": "none"}),
        "approval": {"status": "none"}, "created_at": store.now(),
        "summary_ja": dim.get("summary_ja", ""),
    }
    reasons = {(r.get("part_id"), r.get("name")): r.get("reason_ja", "") for r in dim.get("params", [])}

    def rows():
        out = _param_rows(design["params"], {tuple(k.split("|")): v for k, v in design["sources"].items()})
        for r in out:
            r["reason_ja"] = reasons.get((r["part_id"], r["name"])) or {
                "measured": "採寸の値から決めました", "rule": "決まった式で決めました", "interview": "質問の答えから決めました",
                "ai": "要望に合わせて調整しました", "user": "あなたが変えました"}.get(r["source"], "既定の値です")
        return out

    if not result["ok"]:
        design["status"] = "needs_attention"
        design["review"] = {"rounds": [], "final_verdict": "revise",
                            "unresolved_issues": [{"severity": "high", "description_ja": "形の検査に通りませんでした：" + "／".join(VIOLATION_JA.get(v, v) for v in result["violations"])}]}
    try:
        _render_design(case, design)
    except Exception as e:  # noqa: BLE001
        design["status"] = "failed"
        design["error"] = {"code": "RENDER_FAILED", "message": str(e)[:300]}
        design["param_rows"] = rows()
        return design
    if design["status"] != "needs_attention":
        # 確認と直しのループ（§5）。最大3回。微調整のあとは1回だけ
        rounds, max_rounds, prev_values = [], (3 if parent is None else 1), {}
        for r in range(1, max_rounds + 1):
            design["progress"] = {"step": "reviewing", "round": r, "max_rounds": max_rounds}
            rev = ai.review(design["files"]["views"], design["params"], r, store.FILES) if ai is not gemini_mock                 else ai.review(design["files"]["views"], design["params"], r)
            rounds.append({"round": r, **rev})
            serious = [i for i in rev.get("issues", []) if i.get("severity") in ("high", "medium")]
            all_pass = all(c.get("pass") for c in rev.get("checks", [])) and len(rev.get("checks", [])) == 5
            if rev.get("verdict") == "ok" and all_pass and not serious and not rev.get("changes"):
                design["status"] = "ready"
                break
            if rev.get("verdict") == "ok" or not rev.get("changes") or r == max_rounds:
                design["status"] = "needs_attention"
                break
            before = copy.deepcopy(design["params"])
            srcs = {tuple(k.split("|")): v for k, v in design["sources"].items()}
            nv, applied = _apply_ai(design["params"], rev["changes"], design["variant"], b, srcs)
            design["nut_variant"] = nv or design["nut_variant"]
            design["sources"] = {f"{k[0]}|{k[1]}": v for k, v in srcs.items()}
            oscillating = any(prev_values.get(n) == design["params"]["grip_body"].get(n) for n in applied if n in design["params"]["grip_body"])
            prev_values.update({n: before["grip_body"].get(n) for n in applied if n in before["grip_body"]})
            new_params, res2, _ = _autofix(copy.deepcopy(design["params"]), design["variant"], td, b)
            if not res2["ok"] or not applied or oscillating:
                design["params"] = before  # 直せなければ、前に通った形のまま要確認で終える
                design["status"] = "needs_attention"
                break
            design["params"], design["validation"] = new_params, res2
            _render_design(case, design)
        design["review"] = {"rounds": rounds, "final_verdict": rounds[-1].get("verdict"),
                            "unresolved_issues": [] if design["status"] == "ready" else (
                                rounds[-1].get("issues") or [{"severity": "medium", "description_ja": "AIは修正が必要と判定しましたが、修正案を出せませんでした"}])}
    design["param_rows"] = rows()
    design["progress"] = {"step": "done"}
    return design


def prepare_print(case: dict, design: dict) -> dict:
    d = store.design_dir(case["case_id"], design["design_id"])
    vars_ = _scad_vars(design["params"], design["variant"], design["nut_variant"],
                       case["requirements"]["hand_side"], mode="print", quality="print")
    out = d / "print.stl"
    scad.render_stl(vars_, out)
    mc = scad.mesh_check(out, 2)
    if not mc["ok"]:
        raise RuntimeError("印刷用の形の検査に通りませんでした: " + ", ".join(mc["problems"]))
    design["files"]["print_stl"] = store.rel(out)
    design["print_check"] = mc
    design["print_prepared_at"] = store.now()
    return design
