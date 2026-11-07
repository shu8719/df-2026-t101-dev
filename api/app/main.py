"""生成API（プロトタイプ版）。docs/api.md のうち、流れを最後まで通すのに要るものだけ。

プロトタイプでの代わり：
- 認証：Firebaseの代わりに `X-User` ヘッダー（なければ demo-user）
- Firestore・Storage：手元のJSONとファイル（api/.data）。ブラウザは GET で状態を読む
- Gemini・hand-mesh：モック
- demo_mode：オン（OTの確認なしで印刷用STLを作れる）
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import handmodel as hm
from . import pipeline, store
from .pipeline import ai
from .validator import CATALOG

app = FastAPI(title="自助具ジェネレーター 生成API（プロトタイプ）")
app.add_middleware(CORSMiddleware, allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
                   allow_methods=["*"], allow_headers=["*"])

DEMO_MODE = True
THERAPISTS = {"ot.demo@example.com": "デモOT"}
SAMPLE = Path(__file__).resolve().parents[2] / "schemas" / "measurement.sample.json"


def err(status: int, code: str, message: str, retryable=False, details=None):
    raise HTTPException(status, {"error": {"code": code, "message": message, "retryable": retryable, "details": details or []}})


def get_case(case_id: str, user: str) -> dict:
    c = store.load_case(case_id)
    if c is None:
        err(404, "NOT_FOUND", "ケースが見つかりません")
    if c["owner"] != user and c.get("reviewer_email") != user:
        err(403, "FORBIDDEN", "このケースを見る権限がありません")
    return c


def find_design(case: dict, design_id: str) -> dict:
    for d in case.get("designs", []):
        if d["design_id"] == design_id:
            return d
    err(404, "NOT_FOUND", "版が見つかりません")


def ai_call(fn, *a, **k):
    """Geminiの呼び出し。失敗したら AI_UNAVAILABLE（503）にする。"""
    try:
        return fn(*a, **k)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "AI_OUTPUT_INVALID" in msg:
            err(502, "AI_OUTPUT_INVALID", "AIの返事を読み取れませんでした。もう一度試してください", retryable=True, details=[msg[:300]])
        err(503, "AI_UNAVAILABLE", "AIが混み合っているか、つながりません。少し待ってもう一度試してください", retryable=True, details=[msg[:300]])


@app.get("/healthz")
def healthz():
    import os
    return {"ok": True, "demo_mode": DEMO_MODE, "gemini_mode": os.environ.get("GEMINI_MODE", "mock"),
            "gemini_model": os.environ.get("GEMINI_MODEL", "gemini-4-argon") if os.environ.get("GEMINI_MODE") == "live" else None}


@app.get("/v1/parts")
def parts():
    return CATALOG


@app.get("/v1/therapists")
def therapists():
    return [{"email": e, "name": n} for e, n in THERAPISTS.items()]


@app.get("/v1/sample-measurement")
def sample_measurement():
    """プロトタイプ用：動画の代わりに使うサンプルの採寸値。"""
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


class NewCase(BaseModel):
    title: str = "新しい道具"


@app.post("/v1/cases", status_code=201)
def create_case(body: NewCase, x_user: str = Header("demo-user")):
    c = {"case_id": store.new_id("c"), "owner": x_user, "title": body.title, "status": "interviewing",
         "demo": DEMO_MODE, "requirements": {}, "notes": [], "designs": [], "current_design_id": None,
         "created_at": store.now()}
    store.save_case(c)
    return {"case_id": c["case_id"], "status": c["status"], "demo": c["demo"]}


@app.get("/v1/cases")
def cases(x_user: str = Header("demo-user")):
    return [{k: c.get(k) for k in ("case_id", "title", "status", "current_design_id", "updated_at", "demo")}
            for c in store.list_cases(x_user)]


@app.get("/v1/cases/{case_id}")
def case_detail(case_id: str, x_user: str = Header("demo-user")):
    return get_case(case_id, x_user)


class Requirements(BaseModel):
    activity: str = Field(pattern="^(draw|write|eat|other)$")
    tool_type: str = Field(pattern="^(brush|pen|spoon|other)$")
    hand_side: str = Field(pattern="^(right|left)$")
    tool_shaft_size: str = Field(pattern="^(thin|medium|thick|unknown)$")
    tool_shaft_shape: str = Field(pattern="^(round|flat)$")
    nut_operator: str = Field(pattern="^(self|self_weak|helper)$")
    grip_strength: str = Field(pattern="^(firm|light|weak)$")
    capture_by: str = Field(pattern="^(self|helper)$")


@app.put("/v1/cases/{case_id}/requirements")
def put_requirements(case_id: str, body: Requirements, x_user: str = Header("demo-user")):
    c = get_case(case_id, x_user)
    r = body.model_dump()
    assumptions = []
    size = r["tool_shaft_size"]
    if size == "unknown":
        size = pipeline.DEFAULT_SIZE.get(r["tool_type"], "medium")
        assumptions.append(f"柄の太さが分からないため「{size}」として扱いました")
    r["tool_shaft_diameter_mm"] = pipeline.SIZE_TO_DIAMETER[size]
    r["assumptions"] = assumptions
    r["notes"] = c["requirements"].get("notes", [])
    c["requirements"] = r
    if r["activity"] != "other":
        c["status"] = "measuring"
    store.save_case(c)
    return {"requirements": r, "case_status": c["status"]}


class Chat(BaseModel):
    message: str = Field(max_length=500)


@app.post("/v1/cases/{case_id}/interview")
def interview(case_id: str, body: Chat, x_user: str = Header("demo-user")):
    c = get_case(case_id, x_user)
    turn = ai_call(ai.interview, body.message, c["requirements"])
    c["requirements"].setdefault("notes", []).extend(turn["notes"])
    c["turn_count"] = c.get("turn_count", 0) + 1
    store.save_case(c)
    return {"turn": turn, "requirements": {"notes": c["requirements"]["notes"]}, "case_status": c["status"],
            "turn_count": c["turn_count"]}


@app.post("/v1/cases/{case_id}/consent")
def consent(case_id: str, x_user: str = Header("demo-user")):
    c = get_case(case_id, x_user)
    c["mesh_consent_at"] = store.now()
    store.save_case(c)
    return {"mesh_consent_at": c["mesh_consent_at"]}


@app.put("/v1/cases/{case_id}/measurement")
def put_measurement(case_id: str, body: dict, dry_run: bool = False, x_user: str = Header("demo-user")):
    c = get_case(case_id, x_user)
    try:
        model = hm.build(body)
    except (KeyError, TypeError, ValueError) as e:
        err(422, "MEASUREMENT_INVALID", "採寸データの形が正しくありません", details=[str(e)])
    hand_model = hm.to_json(model)
    if not dry_run:
        c["measurement"] = body
        c["hand_model"] = hand_model
        c["status"] = "designing"
        c["current_design_id"] = None
        store.save_case(c)
    return {"accepted": True, "warnings": hand_model["warnings"], "hand_model": hand_model, "case_status": c["status"]}


class Style(BaseModel):
    color: str = Field("#3A7CA5", pattern="^#[0-9A-Fa-f]{6}$")
    pattern: str = Field("none", pattern="^(none|rings|dots)$")


class NewDesign(BaseModel):
    style: Style = Style()


@app.post("/v1/cases/{case_id}/designs")
def create_design(case_id: str, body: NewDesign, x_user: str = Header("demo-user")):
    c = get_case(case_id, x_user)
    if not c.get("measurement") or not c.get("requirements"):
        err(409, "CONFLICT", "先に質問への答えと採寸を保存してください")
    d = ai_call(pipeline.create_design, c, style=body.style.model_dump())
    c.setdefault("designs", []).append(d)
    c["current_design_id"] = d["design_id"]
    c["status"] = "previewing"
    store.save_case(c)
    return {"design": d}


class Refine(BaseModel):
    instruction: str | None = Field(None, max_length=500)
    param_changes: list[dict] | None = None
    style: Style | None = None


@app.post("/v1/cases/{case_id}/designs/{design_id}/refine")
def refine(case_id: str, design_id: str, body: Refine, x_user: str = Header("demo-user")):
    c = get_case(case_id, x_user)
    parent = find_design(c, design_id)
    if body.style is not None and body.instruction is None and body.param_changes is None:
        # 色だけの変更は版を作らない（模様は形が変わるので、プロトタイプでは未対応）
        parent["style"] = body.style.model_dump()
        store.save_case(c)
        return {"design": parent}
    if body.instruction:
        r = ai_call(ai.refine, body.instruction, parent["params"])
        if r["clarify_ja"]:
            return {"clarify_ja": r["clarify_ja"]}
        changes, origin = r["changes"], "refine_text"
    else:
        changes, origin = body.param_changes or [], "refine_params"
    d = ai_call(pipeline.create_design, c, parent=parent, changes=changes, origin=origin)
    c["designs"].append(d)
    c["current_design_id"] = d["design_id"]
    c["status"] = "previewing"
    store.save_case(c)
    return {"design": d}


@app.post("/v1/cases/{case_id}/designs/{design_id}/prepare-print")
def prepare_print(case_id: str, design_id: str, x_user: str = Header("demo-user")):
    c = get_case(case_id, x_user)
    if not c.get("demo"):
        err(403, "FORBIDDEN", "デモ用のケースではありません。OTに確認を頼んでください")
    d = find_design(c, design_id)
    try:
        pipeline.prepare_print(c, d)
    except Exception as e:  # noqa: BLE001
        err(500, "RENDER_FAILED", "印刷用のデータを作れませんでした", details=[str(e)[:300]])
    store.save_case(c)
    return {"design": d}


class ReviewRequest(BaseModel):
    reviewer_email: str
    design_id: str


@app.post("/v1/cases/{case_id}/review-request")
def review_request(case_id: str, body: ReviewRequest, x_user: str = Header("demo-user")):
    c = get_case(case_id, x_user)
    if body.reviewer_email not in THERAPISTS:
        err(422, "REVIEWER_NOT_ALLOWED", "このアドレスはOTとして登録されていません")
    d = find_design(c, body.design_id)
    pipeline.prepare_print(c, d)          # 依頼のときに印刷用STLを作る
    d["approval"] = {"status": "requested", "reviewer_email": body.reviewer_email, "requested_at": store.now()}
    c["reviewer_email"] = body.reviewer_email
    c["status"] = "in_review"
    store.save_case(c)
    return {"case_status": c["status"], "review_url": f"/review/{case_id}"}


class Approval(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    comment_ja: str = ""


@app.post("/v1/cases/{case_id}/designs/{design_id}/approval")
def approval(case_id: str, design_id: str, body: Approval, x_user: str = Header("demo-user")):
    c = get_case(case_id, x_user)
    if x_user != c.get("reviewer_email"):
        err(403, "FORBIDDEN", "依頼されたOTだけが確認できます")
    d = find_design(c, design_id)
    d["approval"].update({"status": "approved" if body.decision == "approve" else "rejected",
                          "decided_at": store.now(), "comment_ja": body.comment_ja})
    c["status"] = "approved" if body.decision == "approve" else "changes_requested"
    store.save_case(c)
    return {"approval": d["approval"], "case_status": c["status"]}


@app.get("/files/{path:path}")
def files(path: str):
    p = (store.FILES / path).resolve()
    if not str(p).startswith(str(store.FILES.resolve())) or not p.exists():
        raise HTTPException(404)
    return FileResponse(p)
