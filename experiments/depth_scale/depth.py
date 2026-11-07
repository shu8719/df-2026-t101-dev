"""③ フレーム → 点のまわりの深度と焦点距離（docs/depth-scale/scripts.md §5）。

条件 A：フレームそのまま・焦点距離もAI、B：本番と同じ切り抜き・焦点距離もAI、C：フレームそのまま・機種の焦点距離を与える。
深度マップの全体は保存せず、手首と指の付け根の5点のまわり 31×31px の深度（mm）だけを保存する。

使い方：python depth.py --rec p1_t1 --cond A   （--cond A,B,C で3つとも）
        --model constant は、重みなしで流れだけを確かめるための偽物（深度300mm一定）
"""
from __future__ import annotations

import argparse
import math
import platform
import sys
import time
from pathlib import Path

import cv2
import numpy as np

import common


class ConstantBackend:
    """動作確認用の偽物。どの点も深度300mm、焦点距離は35mm換算26mm相当。結果を実験に使ってはいけない"""

    name = "constant"
    version = "constant-300mm"

    def infer(self, rgb: np.ndarray, f_px: float | None) -> tuple[np.ndarray, float]:
        h, w = rgb.shape[:2]
        f = f_px if f_px else common.f_px_from_35mm(26.0, w, h)
        return np.full((h, w), 300.0, dtype=np.float32), float(f)

    def device_name(self) -> str:
        return "cpu"


class DepthProBackend:
    """Apple Depth Pro。深度は m で返るので mm に直す。f_px を与えなければ焦点距離も推定する"""

    name = "depth_pro"

    def __init__(self, checkpoint: Path | None):
        import dataclasses

        import depth_pro  # ライセンスの確認（DS1）が済んでから入れる
        import torch

        self.torch = torch
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        kw = {"device": self.device, "precision": torch.half if self.device.type == "cuda" else torch.float32}
        if checkpoint is not None:
            from depth_pro.depth_pro import DEFAULT_MONODEPTH_CONFIG_DICT  # 要確認：版によって場所が違うかもしれない
            kw["config"] = dataclasses.replace(DEFAULT_MONODEPTH_CONFIG_DICT, checkpoint_uri=str(checkpoint))
        self.model, self.transform = depth_pro.create_model_and_transforms(**kw)
        self.model.eval()
        try:
            from importlib.metadata import version
            self.version = version("depth_pro")
        except Exception:  # noqa: BLE001
            self.version = "unknown"

    def infer(self, rgb: np.ndarray, f_px: float | None) -> tuple[np.ndarray, float]:
        with self.torch.no_grad():
            pred = self.model.infer(self.transform(rgb), f_px=f_px)
        depth_mm = pred["depth"].float().cpu().numpy() * 1000.0
        return depth_mm.astype(np.float32), float(pred["focallength_px"])

    def device_name(self) -> str:
        return self.torch.cuda.get_device_name(0) if self.device.type == "cuda" else "cpu"


def make_backend(name: str, checkpoint: Path | None):
    if name == "constant":
        return ConstantBackend()
    if name == "depth_pro":
        return DepthProBackend(checkpoint)
    raise SystemExit(f"知らないモデルです：{name}")


def resize_to(depth: np.ndarray, w: int, h: int) -> np.ndarray:
    if depth.shape == (h, w):
        return depth
    return cv2.resize(depth, (w, h), interpolation=cv2.INTER_LINEAR)


def device_f_px(rec: dict, w: int, h: int) -> float | None:
    f35 = common.to_float(rec.get("focal_35mm_mm"))
    return common.f_px_from_35mm(f35, w, h) if math.isfinite(f35) else None


def run(rec_id: str, cond: str, backend, force: bool) -> None:
    out_npz = common.DATA / "depth" / rec_id / f"{cond}.npz"
    out_json = out_npz.with_suffix(".json")
    if out_json.exists() and not force:
        print(f"{rec_id} {cond}: 推定済み（作り直すなら --force）")
        return
    fdir = common.DATA / "frames" / rec_id
    frames = {f["index"]: f for f in common.load_json(fdir / "frames.json")["frames"]}
    lms = [r for r in common.load_json(common.DATA / "landmarks" / f"{rec_id}.json")["frames"] if r["used"]]
    rec = next((r for r in common.recordings() if r["rec_id"] == rec_id), {})

    patches: dict[str, np.ndarray] = {}
    rows = []
    for lm in lms:
        fr = frames[lm["index"]]
        w, h = fr["width"], fr["height"]
        bgr = cv2.imread(str(fdir / f"{fr['index']:03d}.jpg"))
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        pts = lm["points_px"]
        row = {"index": fr["index"]}
        if cond in ("A", "C"):
            given = None
            if cond == "C":
                given = device_f_px(rec, w, h)
                if given is None:
                    print(f"{rec_id}: recordings.csv に focal_35mm_mm がないので、条件Cを飛ばします")
                    return
            t0 = time.perf_counter()
            depth, f = backend.infer(rgb, given)
            row["infer_s"] = round(time.perf_counter() - t0, 4)
            depth = resize_to(depth, w, h)
            row["f_px"] = given if given is not None else f
            row["f_source"] = "device" if given is not None else "model"
            offset = (0.0, 0.0)
        elif cond == "B":
            x0, y0, x1, y1 = common.crop_box(pts, w, h)
            x0, y0, x1, y1 = int(math.floor(x0)), int(math.floor(y0)), int(math.ceil(x1)), int(math.ceil(y1))
            crop = rgb[y0:y1, x0:x1]
            cw, ch = x1 - x0, y1 - y0
            s = common.CROP_LONG_SIDE / max(cw, ch)
            small = cv2.resize(crop, (max(1, round(cw * s)), max(1, round(ch * s))), interpolation=cv2.INTER_AREA)
            t0 = time.perf_counter()
            depth_small, f_crop = backend.infer(small, None)
            row["infer_s"] = round(time.perf_counter() - t0, 4)
            depth = resize_to(depth_small, cw, ch)  # 深度（mm）は縮めても変わらない
            row["f_px"] = common.f_crop_to_orig(f_crop, max(cw, ch))
            row["f_source"] = "model"
            row["crop"] = [x0, y0, x1, y1]
            offset = (float(x0), float(y0))
        else:
            raise SystemExit(f"知らない条件です：{cond}")
        for p in common.DEPTH_POINTS:
            u, v = pts[p]
            patches[f"f{fr['index']:03d}_p{p}"] = common.extract_patch(depth, u - offset[0], v - offset[1])
        rows.append(row)

    out_npz.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out_npz, **patches)
    common.save_json(out_json, {
        "rec_id": rec_id, "cond": cond, "model": backend.name, "model_version": backend.version,
        "device": backend.device_name(), "python": platform.python_version(), "frames": rows,
    })
    t = common.median(r["infer_s"] for r in rows)
    print(f"{rec_id} {cond}: {len(rows)} 枚を推定（1枚 {t:.2f} 秒、{backend.device_name()}）")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rec")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--cond", default="A", help="A・B・C をカンマ区切りで（例：A,B,C）")
    ap.add_argument("--model", default="depth_pro", choices=["depth_pro", "constant"])
    ap.add_argument("--checkpoint", type=Path, help="Depth Pro の重み（depth_pro.pt）の場所。省略すると既定の場所")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    ids = common.rec_ids(a.rec, a.all)
    backend = make_backend(a.model, a.checkpoint)
    for rid in ids:
        for c in a.cond.split(","):
            run(rid, c.strip().upper(), backend, a.force)


if __name__ == "__main__":
    sys.exit(main())
