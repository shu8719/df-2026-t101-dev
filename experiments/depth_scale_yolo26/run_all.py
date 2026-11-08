r"""写真の一覧に対して、各モデルの try_image をまとめて動かす（docs/depth-scale-yolo26/scripts.md §1）。

順番：Depth Pro（焦点距離の物差し）→ MoGe-2（vitl）→ Depth Anything 3 → MapAnything → YOLO26 Depth → calibration.py
結果の JSON がすでにあるものは飛ばす（--force で作り直す）。どれも共通の環境の python で動かす。

使い方：..\depth_scale\.venv\Scripts\python run_all.py [--only yolo26] [--force]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from yolo26_backend import EXP

PY = Path(sys.executable)
PHOTO_DIR = EXP / "depth_scale" / "data"
LOG = Path(__file__).resolve().parent / "data" / "progress.txt"  # 進み具合（VS Code で開けば見られる。progress.py も読む）

# （名前、フォルダ、スクリプトと引数、結果の JSON の名前）
STEPS = [
    ("depthpro", "depth_scale", ["try_image.py"], "data/vis/{stem}_depthpro.json"),
    ("moge2", "depth_scale_moge2", ["try_image_moge.py", "--model", "vitl"], "data/vis/{stem}_moge2_vitl.json"),
    ("da3", "depth_scale_da3", ["try_image_da3.py", "--combos", "da3+depthpro,da3+moge2vitl"], "data/vis/{stem}_da3.json"),
    ("mapanything", "depth_scale_mapanything", ["try_image_mapanything.py"], "data/vis/{stem}_mapanything.json"),
    ("yolo26", "depth_scale_yolo26", ["try_image_yolo26.py"], "data/vis/{stem}_yolo26.json"),
]


def log_progress(done: int, total: int, t0: float, now: str) -> None:
    """プログレスバー・経過時間・残りの見込みを表示し、data/progress.txt にも書く"""
    width = 30
    n = round(width * done / total) if total else width
    el = time.time() - t0
    eta = el / done * (total - done) if done else 0
    line = (f"[{'#' * n}{'-' * (width - n)}] {done}/{total} {100 * done / max(total, 1):5.1f}%  "
            f"経過 {el / 60:4.1f}分  残り約 {eta / 60:4.1f}分  いま：{now}")
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(time.strftime("%H:%M:%S ") + line + "\n")


def photos() -> list[Path]:
    return sorted(p for p in PHOTO_DIR.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", help="動かすモデルをカンマ区切りで（例：yolo26,da3）")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    only = set(a.only.split(",")) if a.only else None
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    jobs = []
    for name, folder, args, out in STEPS:
        if only and name not in only:
            continue
        for ph in photos():
            target = EXP / folder / out.format(stem=ph.stem)
            if a.force or not target.exists():
                jobs.append((name, EXP / folder, args, ph, target))
    LOG.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    for i, (name, cwd, args, ph, target) in enumerate(jobs):
        log_progress(i, len(jobs), t0, f"{name} {ph.name}")
        r = subprocess.run([str(PY), *args, str(ph)], cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0 or not target.exists():
            last = (r.stdout + r.stderr).strip().splitlines()[-3:]
            print(f"  失敗：{name} {ph.name}：{' / '.join(last)}", flush=True)
    log_progress(len(jobs), len(jobs), t0, "補正の評価（calibration.py）")
    subprocess.run([str(PY), "calibration.py"], cwd=EXP / "depth_scale_yolo26", env=env)


if __name__ == "__main__":
    sys.exit(main())
