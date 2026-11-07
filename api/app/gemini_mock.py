"""Geminiのモック（GEMINI_MODE=mock）。出力の形は docs/generation-pipeline.md §3 のスキーマに合わせる。

本物のGeminiに差し替えるときは、同じ関数名・同じ戻り値の形で gemini_live.py を作る。
"""
from __future__ import annotations

import re


def interview(message: str, requirements: dict) -> dict:
    notes = []
    m = message.strip()
    if any(w in m for w in ("装具", "伸ばしたい", "固定したい")):
        return {"status": "out_of_scope", "message_ja": "指を伸ばしたり固定したりする装具は、体に合わせた調整が必要なため作れません。作業療法士に相談してください。",
                "choices": [], "notes": [], "suggested_changes": [], "out_of_scope_reason": "orthosis"}
    if "口" in m and ("入れ" in m or "くわえ" in m):
        return {"status": "out_of_scope", "message_ja": "口に入れる部分は作れません（PLAは食品用ではないため）。",
                "choices": [], "notes": [], "suggested_changes": [], "out_of_scope_reason": "mouth_contact"}
    if m:
        notes.append(m[:120])
    suggested = []
    if "左手" in m and requirements.get("hand_side") == "right":
        suggested.append({"field": "hand_side", "value": "left", "reason_ja": "「左手」と書かれていたため"})
    return {"status": "done", "message_ja": "メモに残しました。ほかになければ「とばす」で進んでください。",
            "choices": [], "notes": notes, "suggested_changes": suggested, "out_of_scope_reason": "none"}


def select(requirements: dict, hand_warnings: list[str], fitted_possible: bool) -> dict:
    parts = []
    if fitted_possible:
        parts.append({"part_id": "grip_body", "variant": "fitted", "reason_ja": "測った指の形をくり抜いて、くぼみを指に沿わせます"})
    else:
        parts.append({"part_id": "grip_body", "variant": "oval",
                      "reason_ja": "指に沿わせる形が作れない採寸だったため、手の中で回りにくい楕円のリング状のくぼみにします"})
    parts.append({"part_id": "collet", "variant": "standard", "reason_ja": "柄の太さが少し違っても、ナットを締めて固定できます"})
    weak = requirements.get("nut_operator") == "self_weak"
    parts.append({"part_id": "collet_nut", "variant": "wings" if weak or requirements.get("nut_operator") != "helper" else "knurl",
                  "reason_ja": "指先でつまむのが難しいので、手のひらで回せる羽根付きにします" if weak else "回しやすい羽根付きにします"})
    return {"parts": parts}


def dimension(baseline: list[dict], requirements: dict) -> dict:
    out = []
    for b in baseline:
        reason = {
            "measured": "採寸の値から決めました",
            "rule": "決まった式で決めました",
            "interview": "選択式の答えから決めました",
            "default": "既定の値です",
            "ai": "要望に合わせて調整しました",
        }.get(b["source"], "")
        out.append({**b, "reason_ja": b.get("reason_ja") or reason})
    return {"params": out, "summary_ja": "測った手の形に沿う握りに、ねじ締め式の先端と回しやすいナットを付けました。"}


def review(images: dict, params: dict, round_no: int) -> dict:
    checks = [{"id": f"C{i}", "pass": True, "note_ja": "問題ありません"} for i in range(1, 6)]
    return {"verdict": "ok", "checks": checks, "issues": [], "changes": []}


_WORDS = [
    (r"太く", ("grip_body", ["d_top_mm", "d_bottom_mm"], +1)),
    (r"細く", ("grip_body", ["d_top_mm", "d_bottom_mm"], -1)),
    (r"長く", ("grip_body", ["end_margin_mm", "length_mm"], +1)),
    (r"短く", ("grip_body", ["end_margin_mm", "length_mm"], -1)),
    (r"(くぼみ|沿わせ).*(深く)", ("grip_body", ["press_depth_mm", "groove_depth_mm"], +1)),
    (r"(くぼみ|沿わせ).*(浅く)", ("grip_body", ["press_depth_mm", "groove_depth_mm"], -1)),
]


def refine(instruction: str, current: dict) -> dict:
    amount = 0.05 if "少し" in instruction else 0.15 if "かなり" in instruction else 0.10
    changes = []
    if "ナット" in instruction and ("回しやす" in instruction):
        changes.append({"part_id": "collet_nut", "name": "variant", "value": "wings", "reason_ja": "手のひらで回せる羽根付きにしました"})
    for pat, (part, names, sign) in _WORDS:
        if re.search(pat, instruction):
            for name in names:
                if name in current.get(part, {}):
                    v = current[part][name]
                    step = max(abs(v) * amount, 1.0 if "mm" in name and "depth" not in name else 0.3)
                    changes.append({"part_id": part, "name": name, "value": round(v + sign * step, 1),
                                    "reason_ja": f"「{instruction}」に合わせて変えました"})
            break
    if not changes:
        return {"changes": [], "message_ja": "", "clarify_ja": "どこをどう変えたいか、もう少し教えてください（例：もう少し太く）", "override_by_user": False}
    return {"changes": changes, "message_ja": "直しました。", "clarify_ja": "", "override_by_user": False}
