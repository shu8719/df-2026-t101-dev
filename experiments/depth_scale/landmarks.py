"""② フレーム → 手の21点（docs/depth-scale/scripts.md §4）。

MediaPipe の Python 版の Hand Landmarker を、本番と同じモデル（hand_landmarker.task）で使う。
手が1つだけ見つかり、21点のどれも画面の端（5%以内）にかからないフレームだけを使う。

使い方：python landmarks.py --rec p1_t1   または   --all
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import common

APP_MODEL = common.REPO / "app" / "web" / "mediapipe" / "models" / "hand_landmarker.task"
LOCAL_MODEL = common.HERE / "checkpoints" / "hand_landmarker.task"  # 本番と同じ取得先から取ったもの（コミットしない）
DEFAULT_MODEL = APP_MODEL if APP_MODEL.exists() else LOCAL_MODEL
EDGE = 0.05


def create_landmarker(model_path: Path):
    import mediapipe as mp  # 重いので使うときだけ読む
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    if not model_path.exists():
        raise SystemExit(f"{model_path} がありません。先に bash scripts/fetch_mediapipe.sh を実行するか、--model で指定してください")
    opts = vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(model_path)),
        running_mode=vision.RunningMode.IMAGE,
        num_hands=2,
    )
    return mp, vision.HandLandmarker.create_from_options(opts)


def judge(hands: list, width: int, height: int) -> tuple[bool, str, list[list[float]] | None]:
    """見つかった手から、使うかどうかと、21点（px）を決める"""
    if len(hands) == 0:
        return False, "no_hand", None
    if len(hands) > 1:
        return False, "multiple_hands", None
    pts = [[lm.x * width, lm.y * height] for lm in hands[0]]
    for x, y in pts:
        if x < EDGE * width or x > (1 - EDGE) * width or y < EDGE * height or y > (1 - EDGE) * height:
            return False, "near_edge", pts
    return True, "", pts


def run(rec_id: str, model_path: Path, force: bool, landmarker=None) -> None:
    out = common.DATA / "landmarks" / f"{rec_id}.json"
    if out.exists() and not force:
        print(f"{rec_id}: 手の点は出し済み（作り直すなら --force）")
        return
    fdir = common.DATA / "frames" / rec_id
    meta = common.load_json(fdir / "frames.json")
    mp, lm = landmarker or create_landmarker(model_path)
    rows = []
    for fr in meta["frames"]:
        img = mp.Image.create_from_file(str(fdir / f"{fr['index']:03d}.jpg"))
        res = lm.detect(img)
        used, reason, pts = judge(res.hand_landmarks, fr["width"], fr["height"])
        rows.append({"index": fr["index"], "used": used, "reason": reason, "points_px": pts})
    common.save_json(out, {"rec_id": rec_id, "model": model_path.name, "frames": rows})
    n = sum(r["used"] for r in rows)
    print(f"{rec_id}: {len(rows)} 枚中 {n} 枚で手の21点が取れた")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rec")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="hand_landmarker.task の場所")
    a = ap.parse_args(argv)
    ids = common.rec_ids(a.rec, a.all)
    lmk = create_landmarker(a.model)
    for rid in ids:
        run(rid, a.model, a.force, lmk)


if __name__ == "__main__":
    sys.exit(main())
