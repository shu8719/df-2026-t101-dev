"""hand-mesh: finger flexion angles from cropped hand frames (docs/api.md §4).

Run:  .venv\\Scripts\\python -m uvicorn app:app --port 8081
Images stay in memory only and are never written to disk or logged.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import io
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import numpy as np
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from PIL import Image, ImageOps
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from angles import angles_from_right_keypoints
from backends import BackendManager, BackendUnavailable

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("hand_mesh")

MAX_FRAMES = 8
MAX_FRAME_BYTES = int(os.environ.get("MESH_MAX_FRAME_BYTES", "200000"))
MAX_EXEC_SECONDS = float(os.environ.get("MESH_MAX_EXECUTION_SECONDS", "60"))
REQUIRE_USER = os.environ.get("HAND_MESH_REQUIRE_USER", "0") == "1"
HMAC_KEY = os.environ.get("MESH_RESULT_HMAC_KEY")  # prototype: token only when set
CORS_REGEX = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
EXTRA_ORIGINS = [o.strip() for o in os.environ.get("HAND_MESH_CORS_ORIGINS", "").split(",") if o.strip()]


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, retryable: bool = False):
        self.status, self.code, self.message, self.retryable = status, code, message, retryable


def _err(status: int, code: str, message: str, retryable: bool) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "retryable": retryable,
                      "request_id": "req_" + uuid.uuid4().hex[:6]}}
    return JSONResponse(status_code=status, content=body)


@asynccontextmanager
async def lifespan(app: FastAPI):
    mgr = BackendManager()
    app.state.backends = mgr
    mgr.start(background=True)
    yield


app = FastAPI(title="hand-mesh", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=CORS_REGEX,
    allow_origins=EXTRA_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(ApiError)
async def _api_error(_: Request, e: ApiError):
    return _err(e.status, e.code, e.message, e.retryable)


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, e: RequestValidationError):
    return _err(400, "INVALID_ARGUMENT", "リクエストの形が正しくありません。", False)


@app.get("/healthz")
async def healthz(request: Request):
    return request.app.state.backends.health()


def _decode_jpeg(data: bytes) -> np.ndarray:
    with Image.open(io.BytesIO(data)) as im:
        im = ImageOps.exif_transpose(im)
        return np.asarray(im.convert("RGB"), dtype=np.uint8).copy()


def _result_token(case_id: str, fingers: dict) -> str | None:
    if not HMAC_KEY:
        return None
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    canon = json.dumps({f: v["flexion_deg"] for f, v in fingers.items()}, sort_keys=True, separators=(",", ":"))
    angle_hash = hashlib.sha256(canon.encode()).hexdigest()
    payload = f"v1.{case_id}.{ts}.{angle_hash}"
    sig = hmac.new(HMAC_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


@app.post("/v1/angles")
async def angles(request: Request):
    t0 = time.time()
    user = request.headers.get("x-user", "").strip()
    if REQUIRE_USER and not user:
        raise ApiError(401, "UNAUTHENTICATED", "ログインが必要です。", False)

    ctype = request.headers.get("content-type", "")
    if not ctype.startswith("multipart/form-data"):
        raise ApiError(400, "INVALID_ARGUMENT", "multipart/form-data で送ってください。", False)
    form = await request.form(max_files=MAX_FRAMES + 2)
    try:
        raw_meta = form.get("meta")
        if isinstance(raw_meta, UploadFile):
            raw_meta = (await raw_meta.read()).decode("utf-8")
        meta = json.loads(raw_meta or "")
        if not isinstance(meta, dict):
            raise ValueError
    except (ValueError, UnicodeDecodeError):
        raise ApiError(400, "INVALID_ARGUMENT", "meta（JSON）がありません、または読めません。", False)

    case_id = meta.get("case_id")
    if not isinstance(case_id, str) or not case_id:
        raise ApiError(400, "INVALID_ARGUMENT", "meta.case_id が必要です。", False)
    # Prototype: consent flag in meta. Later: cases/{case_id}.mesh_consent_at in Firestore.
    if meta.get("consent") is not True:
        raise ApiError(422, "CONSENT_REQUIRED", "映像を送ることへの同意が記録されていません。同意の画面からやり直してください。", False)
    hand_side = meta.get("hand_side")
    if hand_side not in ("right", "left"):
        raise ApiError(400, "INVALID_ARGUMENT", "meta.hand_side は 'right' か 'left' にしてください。", False)

    names = [f"frame_{i}" for i in range(MAX_FRAMES)]
    extra = [k for k in form.keys() if k.startswith("frame_") and k not in names]
    if extra:
        raise ApiError(400, "INVALID_ARGUMENT", f"フレームは最大{MAX_FRAMES}枚（frame_0〜frame_7）です。", False)
    images = []
    try:
        for name in names:
            part = form.get(name)
            if part is None:
                continue
            data = await part.read() if isinstance(part, UploadFile) else None
            if not data:
                raise ApiError(400, "INVALID_ARGUMENT", f"{name} は画像ファイルで送ってください。", False)
            if len(data) > MAX_FRAME_BYTES:
                raise ApiError(400, "INVALID_ARGUMENT", f"{name} が大きすぎます（1枚{MAX_FRAME_BYTES // 1000}KBまで）。", False)
            try:
                images.append(_decode_jpeg(data))
            except Exception:
                raise ApiError(400, "INVALID_ARGUMENT", f"{name} を画像として読めません。", False)
            del data
    finally:
        await form.close()
    if not images:
        raise ApiError(400, "INVALID_ARGUMENT", "フレーム（frame_0〜）が1枚もありません。", False)

    mgr: BackendManager = request.app.state.backends
    try:
        backend = mgr.current()
    except BackendUnavailable as e:
        log.info("angles: frames=%d error=MESH_UNAVAILABLE (%s)", len(images), e)
        raise ApiError(503, "MESH_UNAVAILABLE", "角度を計算する準備をしています。しばらくして自動でやり直します。", True)

    try:
        kps = await asyncio.wait_for(run_in_threadpool(backend.infer, images, hand_side), timeout=MAX_EXEC_SECONDS)
    except asyncio.TimeoutError:
        log.info("angles: frames=%d error=MESH_UNAVAILABLE (timeout %.0fs)", len(images), MAX_EXEC_SECONDS)
        raise ApiError(503, "MESH_UNAVAILABLE", "角度の計算が時間内に終わりませんでした。", True)
    except BackendUnavailable:
        raise ApiError(503, "MESH_UNAVAILABLE", "角度を計算する準備をしています。", True)
    except Exception as e:  # noqa: BLE001 - never echo image data
        log.error("angles: frames=%d error=MESH_UNAVAILABLE (%s)", len(images), type(e).__name__)
        raise ApiError(503, "MESH_UNAVAILABLE", "角度の計算に失敗しました。", True)
    finally:
        images.clear()

    fingers, used = angles_from_right_keypoints(kps)
    if not fingers:
        log.info("angles: frames=%d used=0 error=NO_HAND_DETECTED %.2fs", len(kps), time.time() - t0)
        raise ApiError(422, "NO_HAND_DETECTED", "どのフレームでも手の姿勢が分かりませんでした。撮り直してください。", False)

    warnings = []
    if used < len(kps):
        warnings.append("MESH_FRAMES_DROPPED")  # some frames gave no hand pose (frames_used < sent)
    body = {"method": "mesh_recovery", "model": backend.model, "fingers": fingers, "warnings": warnings}
    token = _result_token(case_id, fingers)
    if token:
        body["result_token"] = token
    log.info("angles: backend=%s frames=%d used=%d %.2fs", backend.name, len(kps), used, time.time() - t0)
    return body
