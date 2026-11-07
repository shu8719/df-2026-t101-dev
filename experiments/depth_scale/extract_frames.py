"""① 動画 → フレーム（docs/depth-scale/scripts.md §3）。

1秒に6枚の候補を取り、ぼけの少ない上位3枚/秒を残して、長い辺を最大1280pxに縮めて保存する。
本番の選び方（docs/measurement.md §3.1）と同じ。

使い方：python extract_frames.py --rec p1_t1   または   --all
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

import common

CANDIDATES_PER_S = 6
KEEP_PER_S = 3
MAX_LONG_SIDE = 1280
SHARP_LONG_SIDE = 256


def sharpness(bgr: np.ndarray) -> float:
    """長い辺256pxの白黒に縮めた画像のラプラシアンの分散（大きいほどくっきり）"""
    h, w = bgr.shape[:2]
    s = SHARP_LONG_SIDE / max(h, w)
    small = cv2.resize(bgr, (max(8, round(w * s)), max(8, round(h * s))), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)
    return float(cv2.Laplacian(gray, cv2.CV_32F).var())


def to_h264(src: Path, tmp_dir: Path) -> Path:
    """OpenCV で読めない動画（iPhone の HEVC など）を、ffmpeg で H.264 に変える"""
    if not shutil.which("ffmpeg"):
        raise SystemExit("動画を読めませんでした。ffmpeg を入れてから、もう一度実行してください")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    dst = tmp_dir / (src.stem + "_h264.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-c:v", "libx264", "-crf", "12",
                    "-pix_fmt", "yuv420p", "-an", str(dst)], check=True)
    return dst


def read_candidates(path: Path) -> tuple[list[tuple[float, np.ndarray]], tuple[int, int]]:
    """1秒に6枚の候補（時刻 秒、画像）。OpenCV は回転の情報を既定で反映する"""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return [], (0, 0)
    cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
    out: list[tuple[float, np.ndarray]] = []
    next_t = 0.0
    size = (0, 0)
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        size = (frame.shape[1], frame.shape[0])
        if t + 1e-6 >= next_t:
            out.append((t, frame))
            next_t += 1.0 / CANDIDATES_PER_S
    cap.release()
    return out, size


def extract(rec_id: str, force: bool) -> None:
    src = common.DATA / "raw" / f"{rec_id}.mp4"
    out_dir = common.DATA / "frames" / rec_id
    if (out_dir / "frames.json").exists() and not force:
        print(f"{rec_id}: 取り出し済み（作り直すなら --force）")
        return
    if not src.exists():
        raise SystemExit(f"{src} がありません")
    cands, size = read_candidates(src)
    if not cands:
        cands, size = read_candidates(to_h264(src, common.DATA / "tmp"))
    if not cands:
        raise SystemExit(f"{rec_id}: フレームを取り出せませんでした")

    # 1秒ごとに、ぼけの少ない上位3枚を残す
    by_sec: dict[int, list[tuple[float, float, np.ndarray]]] = {}
    for t, img in cands:
        by_sec.setdefault(int(t), []).append((sharpness(img), t, img))
    kept = []
    for sec in sorted(by_sec):
        kept += sorted(by_sec[sec], key=lambda x: -x[0])[:KEEP_PER_S]
    kept.sort(key=lambda x: x[1])

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    w0, h0 = size
    scale = min(1.0, MAX_LONG_SIDE / max(w0, h0))
    w, h = round(w0 * scale), round(h0 * scale)
    frames = []
    for i, (blur, t, img) in enumerate(kept):
        if scale < 1.0:
            img = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(out_dir / f"{i:03d}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        frames.append({"index": i, "t_s": round(t, 3), "width": w, "height": h, "blur": round(blur, 2)})
    common.save_json(out_dir / "frames.json", {
        "rec_id": rec_id, "video_width": w0, "video_height": h0, "scale": scale,
        "candidates": len(cands), "frames": frames,
    })
    print(f"{rec_id}: 候補 {len(cands)} 枚 → {len(frames)} 枚を保存（{w}×{h}）")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rec")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    for rid in common.rec_ids(a.rec, a.all):
        extract(rid, a.force)


if __name__ == "__main__":
    sys.exit(main())
