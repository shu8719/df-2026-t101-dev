"""使ったあとの報告から、次にすることと直す案を決める（docs/adr/0015-refit-reorder.md、api.md §3.14）。
Gemini は呼ばない。直す量は 0.25mm に固定（クリップの固定STLの刻みと同じ）。"""
from __future__ import annotations

RESULTS = ("good", "loose", "tight_pain", "red", "tool_slips")
STEP_MM = 0.25

STOP_JA = "すぐに使うのをやめて、作業療法士に相談してください。"
GOOD_JA = "ありがとうございます。記録しました。"
CONSULT_JA = "これ以上は自動で直せません。作業療法士に相談してください。"
FELT_JA = {
    "loose": "まず、内側のフェルトを厚いものに替えてみてください。刷り直さずに合うことがあります。",
    "tight_pain": "まず、内側のフェルトを薄いものに替えてみてください。刷り直さずに合うことがあります。",
}
REFINE_JA = "下の内容で作り直せます。作り直した形も、作業療法士の確認を受けてから刷ります。"
RESULT_JA = {"loose": "ゆるい", "tight_pain": "きつい・痛い", "tool_slips": "道具が抜ける"}


def _fmt(v: float) -> str:
    return f"{v:g}"


def advise(*, part: str, result: str, felt_changed: bool, current: float, lo: float, hi: float,
           label: str = "", attachment_id: str | None = None, report_id: str) -> dict:
    """答えから次にすること（kind・message_ja・proposal）を決める。
    part は "cover" か取り付け具の ID。current はカバーならすき間、クリップなら柄の太さ（mm）"""
    if result == "red":
        return {"kind": "stop", "message_ja": STOP_JA, "proposal": None}
    if result == "good":
        return {"kind": "none", "message_ja": GOOD_JA, "proposal": None}
    cover = part == "cover"
    # カバー：ゆるい → すき間を狭める。クリップ：ゆるい・抜ける → 柄の太さの値を小さくして穴を締める。きついは逆
    to = round(current - STEP_MM if result in ("loose", "tool_slips") else current + STEP_MM, 2)
    if not lo - 1e-9 <= to <= hi + 1e-9:
        return {"kind": "consult", "message_ja": CONSULT_JA, "proposal": None}
    why = f"使ったあとの報告（{RESULT_JA[result]}）に合わせて"
    if cover:
        verb = "狭め" if to < current else "広げ"
        proposal = {
            "part": "cover", "name": "clearance_mm", "from": current, "to": to,
            "summary_ja": f"カバーとこぶしのすき間を {_fmt(current)}mm から {_fmt(to)}mm に{verb}ます",
            "request": {"param_changes": [{"part_id": "cover", "name": "clearance_mm", "value": to,
                                           "reason_ja": f"{why}、すき間を{_fmt(STEP_MM)}mm{verb}ました"}],
                        "fit_report_id": report_id},
        }
    else:
        tighter = to < current
        proposal = {
            "part": part, "name": "tool_d_mm", "from": current, "to": to,
            "summary_ja": f"{label}のクリップの穴を {_fmt(STEP_MM)}mm {'小さく' if tighter else '大きく'}します"
                          f"（柄の太さの値を {_fmt(current)}mm から {_fmt(to)}mm にします）",
            "request": {"tool_d_mm": to, "attachment_id": attachment_id, "fit_report_id": report_id},
        }
    if cover and not felt_changed:
        return {"kind": "felt", "message_ja": FELT_JA[result], "proposal": proposal}
    return {"kind": "refine", "message_ja": REFINE_JA, "proposal": proposal}
