"""本物のGemini（Gemini Enterprise Agent Platform、旧 Vertex AI）。GEMINI_MODE=live のときに使う。

設定（環境変数）：GOOGLE_CLOUD_PROJECT（必須）、GEMINI_LOCATION（既定 global）、GEMINI_MODEL（既定 gemini-4-argon）。
認証：手元では `gcloud auth application-default login`、Cloud Run ではサービスアカウント（APIキーは使わない）。
出力の形は gemini_mock.py と同じ（docs/generation-pipeline.md §3）。
"""
from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path

from google import genai
from google.genai import types

log = logging.getLogger("gemini")
ROOT = Path(__file__).resolve().parents[2]
CATALOG = json.loads((ROOT / "scad" / "catalog.json").read_text(encoding="utf-8"))

SYSTEM = """あなたは自助具（日常生活の道具を使いやすくする補助具）の設計を手伝うアシスタントです。
- 医療機器や装具（指を伸ばす・固定する・矯正するもの）は扱いません。口に入れる部分も作りません。
- 形は作りません。カタログにある部品と引数だけを使い、カタログにないものを作りません。
- 寸法はmm、角度は度。数値は小数第1位まで。
- 利用者に見せる文（*_ja）は、やさしい日本語で短く書きます。
- 理由には、根拠にした採寸値や質問の答えの名前を挙げます。
- 出力は指定されたJSONスキーマに必ず従います。"""


@lru_cache(maxsize=1)
def _client() -> genai.Client:
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT が設定されていません")
    return genai.Client(
        vertexai=True, project=project, location=os.environ.get("GEMINI_LOCATION", "global"),
        http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(
            attempts=5, initial_delay=1.0, http_status_codes=[408, 429, 500, 502, 503, 504])),
    )


def _model() -> str:
    return os.environ.get("GEMINI_MODEL", "gemini-4-argon")


USAGE = {"input_tokens": 0, "output_tokens": 0, "calls": 0}


def _call(name: str, parts: list, schema: dict, thinking: str = "LOW") -> dict:
    cfg = types.GenerateContentConfig(
        system_instruction=SYSTEM,
        response_mime_type="application/json",
        response_json_schema=schema,
        thinking_config=types.ThinkingConfig(thinking_level=thinking),
        media_resolution=types.MediaResolution.MEDIA_RESOLUTION_MEDIUM,
    )
    last_err = None
    for attempt in range(2):  # R1：形が崩れていたら1回だけ聞き直す
        resp = _client().models.generate_content(model=_model(), contents=parts, config=cfg)
        um = resp.usage_metadata
        if um:
            USAGE["input_tokens"] += um.prompt_token_count or 0
            USAGE["output_tokens"] += (um.candidates_token_count or 0) + (um.thoughts_token_count or 0)
        USAGE["calls"] += 1
        try:
            return json.loads(resp.text)
        except (TypeError, json.JSONDecodeError) as e:
            last_err = e
            parts = parts + [f"前の出力はJSONとして読めませんでした（{e}）。スキーマどおりのJSONだけを出してください。"]
    raise RuntimeError(f"AI_OUTPUT_INVALID: {name}: {last_err}")


CHANGES = {
    "type": "array", "maxItems": 8,
    "items": {"type": "object", "required": ["part_id", "name", "value", "reason_ja"],
              "properties": {"part_id": {"type": "string"}, "name": {"type": "string"},
                             "value": {"anyOf": [{"type": "number"}, {"type": "string"}]}, "reason_ja": {"type": "string"}}},
}


def interview(message: str, requirements: dict) -> dict:
    schema = {
        "type": "object", "required": ["status", "message_ja", "choices", "notes", "suggested_changes", "out_of_scope_reason"],
        "properties": {
            "status": {"enum": ["ask", "done", "out_of_scope"]},
            "message_ja": {"type": "string"},
            "choices": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
            "notes": {"type": "array", "items": {"type": "string"}},
            "suggested_changes": {"type": "array", "items": {"type": "object", "required": ["field", "value", "reason_ja"], "properties": {
                "field": {"enum": ["activity", "tool_type", "hand_side", "tool_shaft_size", "tool_shaft_shape", "nut_operator", "grip_strength", "capture_by"]},
                "value": {"type": "string"}, "reason_ja": {"type": "string"}}}},
            "out_of_scope_reason": {"enum": ["orthosis", "mouth_contact", "unsupported_tool", "medical_claim", "none"]},
        },
    }
    prompt = ("利用者は選択式の質問にすでに答えています。チャットで送られた文を、要件のメモ（notes）に直してください。"
              "足りない点があれば1つだけ聞き返し（status=ask、選択肢は最大4つ）、なければ status=done にします。"
              "選択式の答えと食い違う内容は requirements を直接変えず suggested_changes に入れます。"
              "装具や口に入れる部分の依頼は out_of_scope にし、理由と代わりの案を伝えます。\n"
              f"選択式の答え: {json.dumps(requirements, ensure_ascii=False)}\n利用者の文: {message}")
    return _call("interview", [prompt], schema, "LOW")


def select(requirements: dict, hand_warnings: list[str], fitted_possible: bool) -> dict:
    variants = {p: list(v["variants"].keys()) for p, v in CATALOG["parts"].items()}
    if not fitted_possible:
        variants["grip_body"] = [v for v in variants["grip_body"] if v != "fitted"]
    schema = {"type": "object", "required": ["parts"], "properties": {"parts": {
        "type": "array", "minItems": 3, "maxItems": 3,
        "items": {"type": "object", "required": ["part_id", "variant", "reason_ja"], "properties": {
            "part_id": {"enum": ["grip_body", "collet", "collet_nut"]}, "variant": {"type": "string"}, "reason_ja": {"type": "string"}}}}}}
    prompt = ("部品を選んでください。順番は grip_body、collet、collet_nut の3つです。種類を選ぶ理由を書きます。"
              "握り本体は、fitted が使えるなら基本は fitted（測った指に沿わせる形）にします。"
              "ナットは、指先でつまむのが難しい人（nut_operator=self_weak）には wings にします。\n"
              f"使える種類: {json.dumps(variants, ensure_ascii=False)}\n"
              f"種類の説明: {json.dumps({p: v['variants'] for p, v in CATALOG['parts'].items()}, ensure_ascii=False)}\n"
              f"選択式の答えとメモ: {json.dumps(requirements, ensure_ascii=False)}\n採寸の警告: {hand_warnings}")
    out = _call("select", [prompt], schema, "LOW")
    order = {"grip_body": 0, "collet": 1, "collet_nut": 2}
    out["parts"] = sorted(out["parts"], key=lambda p: order.get(p["part_id"], 9))
    for p in out["parts"]:  # カタログにない種類は使わない（R1）
        if p["variant"] not in variants.get(p["part_id"], []):
            p["variant"] = variants[p["part_id"]][0]
    return out


def dimension(baseline: list[dict], requirements: dict) -> dict:
    schema = {"type": "object", "required": ["params", "summary_ja"], "properties": {
        "params": {"type": "array", "items": {"type": "object", "required": ["part_id", "name", "value", "source", "reason_ja"], "properties": {
            "part_id": {"type": "string"}, "name": {"type": "string"}, "value": {"type": "number"},
            "source": {"enum": ["measured", "rule", "interview", "ai", "default"]}, "reason_ja": {"type": "string"}}}},
        "summary_ja": {"type": "string"}}}
    prompt = ("各引数の値を決め、理由を付けて全部返してください。source が measured・rule・interview の引数は、値を変えずに理由だけ書きます。"
              "それ以外は、要望（メモ・握る力・ナットを回す人）に合わせて範囲の中で調整してよく、変えたら source=ai にします。"
              "握る力が弱い（grip_strength=weak）なら、press_depth_mm を少し深くしてよいです（上限を守る）。\n"
              f"引数（範囲つき）: {json.dumps(baseline, ensure_ascii=False)}\n選択式の答えとメモ: {json.dumps(requirements, ensure_ascii=False)}")
    return _call("dimension", [prompt], schema, "MEDIUM")


def review(images: dict, params: dict, round_no: int, files_root: Path | None = None) -> dict:
    schema = {"type": "object", "required": ["verdict", "checks", "issues", "changes"], "properties": {
        "verdict": {"enum": ["ok", "revise"]},
        "checks": {"type": "array", "minItems": 5, "maxItems": 5, "items": {"type": "object", "required": ["id", "pass", "note_ja"], "properties": {
            "id": {"enum": ["C1", "C2", "C3", "C4", "C5"]}, "pass": {"type": "boolean"}, "note_ja": {"type": "string"}}}},
        "issues": {"type": "array", "items": {"type": "object", "required": ["severity", "description_ja"], "properties": {
            "severity": {"enum": ["high", "medium", "low"]}, "description_ja": {"type": "string"}}}},
        "changes": CHANGES}}
    parts: list = [("4枚の画像は、できた握りを（1）真横（2）90度回した真横（3）真上（4）斜め上から描いたものです。"
                    "青などの色が握りとナット、赤い棒が道具（筆など）の目安、半透明の肌色が測った指のカプセルです。\n"
                    "次を1つずつ判定してください。C1 道具を挟む部分が握りの上端にあり、赤い棒が上に伸びている。"
                    "C2 指のカプセルがくぼみに収まり、握りの外に浮いていない。C3 指が当たる所に尖った角や極端に薄い所がない。"
                    "C4 太さと長さの釣り合いが不自然でない。C5 要望が形に表れている。\n"
                    "寸法の細かい正しさは別の検査で確かめるので、意図と合っているかを見てください。"
                    "直す必要があれば verdict=revise にし、直す引数と値を changes に入れます。\n"
                    f"今の引数: {json.dumps(_strip_caps(params), ensure_ascii=False)}\n確認の回数: {round_no}/3")]
    for name in ("front", "side", "top", "iso"):
        p = Path(images[name]) if files_root is None else files_root / images[name]
        parts.append(types.Part.from_bytes(data=p.read_bytes(), mime_type="image/png"))
    return _call("review", parts, schema, "MEDIUM")


def refine(instruction: str, current: dict) -> dict:
    schema = {"type": "object", "required": ["changes", "message_ja", "clarify_ja", "override_by_user"], "properties": {
        "changes": CHANGES, "message_ja": {"type": "string"}, "clarify_ja": {"type": "string"}, "override_by_user": {"type": "boolean"}}}
    prompt = ("利用者の言葉の指示を、引数の変更に直してください。量の目安：「少し」＝5%（最低1mm）、指定なし＝10%、「かなり」＝15%。"
              "「太く／細く」は d_top_mm と d_bottom_mm、「長く／短く」は length_mm、「くぼみを深く／浅く」は press_depth_mm（fitted）か groove_depth_mm、"
              "「ナットを回しやすく」は collet_nut の variant を wings に（name=variant、value=wings）。"
              "あいまいなら何も変えず clarify_ja に確認の質問を書きます（なければ空文字）。\n"
              f"今の引数: {json.dumps(_strip_caps(current), ensure_ascii=False)}\n指示: {instruction}")
    return _call("refine", [prompt], schema, "LOW")


def _strip_caps(params: dict) -> dict:
    out = {p: {k: v for k, v in vals.items() if k != "capsules"} for p, vals in params.items()}
    return out
