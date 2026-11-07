"""OpenSCADの実行（docs/generation-pipeline.md §6）。

-D の値は、範囲チェックを通った型付きの値だけから、ここで文字列にする。AIの文字列をそのまま渡さない。
"""
from __future__ import annotations

import concurrent.futures as cf
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import trimesh

ROOT = Path(__file__).resolve().parents[2]
SCAD_DIR = ROOT / "scad"
TIMEOUT_S = 60

VIEWS = {  # 名前: --camera の回転 (x, y, z)
    "front": (90, 0, 0),
    "side": (90, 0, 90),
    "top": (0, 0, 0),
    "iso": (60, 0, 35),
}
ENUMS = {"hand": {"right", "left"}, "mode": {"assembled", "print"}, "quality": {"preview", "print"},
         "grip_body_variant": {"fitted", "round", "oval"}, "collet_nut_variant": {"wings", "knurl"}}


def openscad_bin() -> str:
    env = os.environ.get("OPENSCAD_BIN")
    if env:
        return env
    for cand in (r"C:\Program Files\OpenSCAD (Nightly)\openscad.com", "openscad"):
        if shutil.which(cand) or Path(cand).exists():
            return cand
    return "openscad"


def _fmt(name: str, value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return f"{float(value):.2f}"
    if isinstance(value, str):
        if name not in ENUMS or value not in ENUMS[name]:
            raise ValueError(f"文字列の値は選択肢だけ: {name}={value}")
        return f'"{value}"'
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_fmt(name, v) if not isinstance(v, str) else "0" for v in value) + "]"
    raise ValueError(f"渡せない値: {name}")


def defines(vars: dict) -> list[str]:
    args = []
    for k, v in vars.items():
        args += ["-D", f"{k}={_fmt(k, v)}"]
    return args


def _run(args: list[str], cwd: Path) -> None:
    proc = subprocess.run([openscad_bin(), *args], cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT_S)
    if proc.returncode != 0 or "ERROR" in proc.stderr:
        tail = "\n".join(l for l in proc.stderr.splitlines() if not l.startswith("TRACE"))[-800:]
        raise RuntimeError(f"OpenSCADの失敗: {tail}")


def render_stl(vars: dict, out: Path) -> None:
    _run(["-o", str(out), "--export-format", "binstl", *defines(vars), "main.scad"], SCAD_DIR)


def render_views(stl: Path, out_dir: Path, view_vars: dict) -> dict[str, Path]:
    """STLを読み込んで4方向の画像を並行して描く。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="view_"))
    shutil.copy(SCAD_DIR / "view.scad", tmp / "view.scad")
    shutil.copy(stl, tmp / "preview.stl")
    caps = view_vars.get("capsules", [])
    base = ["--preview", "--imgsize=768,768", "--viewall", "--autocenter", "--projection=p",
            "-D", f'grip_color="{view_vars.get("color", "#3A7CA5")}"',
            "-D", f'tool_d={float(view_vars.get("tool_d", 10)):.2f}',
            "-D", f'tool_top_z={float(view_vars.get("tool_top_z", 200)):.2f}',
            "-D", f'hand="{view_vars.get("hand", "right")}"',
            "-D", "capsules=" + "[" + ",".join("[" + ",".join(f"{v:.2f}" for v in c) + "]" for c in caps) + "]",
            "-D", f'clearance={float(view_vars.get("clearance", 0)):.2f}']
    results = {}

    def one(name, rot):
        out = out_dir / f"{name}.png"
        _run(["-o", str(out), f"--camera=0,0,0,{rot[0]},{rot[1]},{rot[2]},0", *base, "view.scad"], tmp)
        return name, out

    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for name, path in ex.map(lambda kv: one(*kv), VIEWS.items()):
            results[name] = path
    shutil.rmtree(tmp, ignore_errors=True)
    return results


def mesh_check(stl: Path, expected_bodies: int, bed=(180, 180, 180)) -> dict:
    """R6（張り出しは、くり抜きの検査で確かめるのでここでは数えない）。"""
    m = trimesh.load_mesh(stl)
    bodies = len(m.split(only_watertight=False))
    ext = m.bounds[1] - m.bounds[0]
    problems = []
    if not m.is_watertight:
        problems.append("NOT_WATERTIGHT")
    if m.volume <= 0:
        problems.append("ZERO_VOLUME")
    if any(e > b for e, b in zip(ext, bed)):
        problems.append("TOO_BIG_FOR_BED")
    return {"ok": not problems, "problems": problems, "bodies": bodies,
            "extent_mm": [round(float(e), 1) for e in ext], "volume_cm3": round(float(m.volume) / 1000, 1)}
