"""手のカプセルモデル、指ごとのすき間、握りの座標系（docs/measurement.md §8）。

手の座標系（右手に正準化したもの。左手は採寸エンジンが左右反転して渡し、OpenSCADで鏡像に戻す）:
  原点 = 手首、x = 人差し指の付け根 → 小指の付け根、y = 手首 → 中指の付け根（x成分を除く）、
  z = 指が曲がる側（手のひら側）。単位はmm。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

FINGERS = ("index", "middle", "ring", "pinky")
SEGMENTS = ("proximal", "middle", "distal")
D_MAX_MM = 55.0
GRID_STEP_MM = 0.5


@dataclass
class Capsule:
    finger: str
    segment: str
    p1: np.ndarray
    p2: np.ndarray
    radius: float


@dataclass
class Cavity:
    diameter_mm: float | None
    center_mm: np.ndarray | None  # 手の座標系
    warning: str | None = None    # CAVITY_OPEN / CAVITY_PARTIAL


@dataclass
class HandModel:
    capsules: list[Capsule]
    cavities: dict[str, Cavity]
    warnings: list[str] = field(default_factory=list)


def _rot(axis: np.ndarray, deg: float) -> np.ndarray:
    """axis まわりに deg 度回す回転行列（右ねじ）。"""
    a = axis / np.linalg.norm(axis)
    t = math.radians(deg)
    k = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(t) * k + (1 - math.cos(t)) * (k @ k)


def finger_chain(mcp_xy, abduction_deg, lengths, flexion):
    """順運動学：J1〜J4 と、曲がる面の基底 (d0, z) を返す。"""
    a = math.radians(abduction_deg)
    d0 = np.array([math.sin(a), math.cos(a), 0.0])
    # a × d0 = +z になる向きで回すと、指は手のひら側（+z）へ曲がる
    axis = np.array([math.cos(a), -math.sin(a), 0.0])
    j1 = np.array([mcp_xy[0], mcp_xy[1], 0.0])
    joints = [j1]
    total = 0.0
    for length, ang in zip(lengths, (flexion["mcp"], flexion["pip"], flexion["dip"])):
        total += ang
        joints.append(joints[-1] + length * (_rot(axis, total) @ d0))
    return joints, d0, np.array([0.0, 0.0, 1.0])


def _seg_dist(p, a, b):
    ab = b - a
    t = np.clip(((p - a) @ ab) / max(ab @ ab, 1e-9), 0.0, 1.0)
    return float(np.linalg.norm(p - (a + t * ab)))


def _point_in_poly(pt, poly):
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xi:
                inside = not inside
    return inside


def _segments_intersect(p1, p2, p3, p4):
    def orient(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    o1, o2, o3, o4 = orient(p1, p2, p3), orient(p1, p2, p4), orient(p3, p4, p1), orient(p3, p4, p2)
    return (o1 * o2 < 0) and (o3 * o4 < 0)


def _is_simple(poly):
    n = len(poly)
    for i in range(n):
        for j in range(i + 1, n):
            if abs(i - j) <= 1 or (i == 0 and j == n - 1):
                continue
            if _segments_intersect(poly[i], poly[(i + 1) % n], poly[j], poly[(j + 1) % n]):
                return False
    return True


def cavity_for_finger(joints, d0, zaxis, radii, palm_thickness, total_flex_deg) -> Cavity:
    """指の曲がる面の中で、手のひらと指に挟まれた最大の円（§8.3）。

    円の中心は「付け根の下の皮膚 → 指の関節 → 指先 → 指先から手のひらへ下ろした点」で囲んだ
    内側に限る（外側を選ばないため）。円の大きさは、手のひらの面と指のカプセルまでの距離で決め、
    閉じる線は越えてよい（指先と手のひらの間が開いていれば、握りはそこから少しはみ出してよい）。
    円が閉じる線を越えたら CAVITY_PARTIAL（指が回り込みきらない）とする。
    """
    origin = joints[0]
    to2d = lambda p: np.array([(p - origin) @ d0, (p - origin) @ zaxis])
    j2d = [to2d(j) for j in joints]
    t = palm_thickness
    if total_flex_deg < 90:
        # 指先が手のひらの方へ戻っていない：囲まれたすき間がない
        return Cavity(None, None, "CAVITY_OPEN")
    base_pt = np.array([0.0, t])
    u_tip = j2d[3][0]
    close_pt = np.array([min(u_tip, 0.0), t])   # 指先が付け根より先なら、付け根の下の点で閉じる
    poly = [base_pt] + ([close_pt] if u_tip < 0 else []) + [j2d[3], j2d[2], j2d[1]]
    poly_t = [tuple(p) for p in poly]
    n = len(poly_t)
    area = 0.5 * abs(sum(poly_t[i][0] * poly_t[(i + 1) % n][1] - poly_t[(i + 1) % n][0] * poly_t[i][1] for i in range(n)))
    if area < 1.0 or not _is_simple(poly_t):
        return Cavity(None, None, "CAVITY_OPEN")
    xs = [p[0] for p in poly_t]
    ys = [p[1] for p in poly_t]
    best_r, best_c = 0.0, None
    for u in np.arange(min(xs), max(xs), GRID_STEP_MM):
        for v in np.arange(t + GRID_STEP_MM, max(ys), GRID_STEP_MM):
            if not _point_in_poly((u, v), poly_t):
                continue
            c = np.array([u, v])
            d_palm = v - t                       # 手のひらの面（付け根より先へも延ばした面）
            d_caps = min(_seg_dist(c, j2d[i], j2d[i + 1]) - radii[i] for i in range(3))
            r = min(d_palm, d_caps)
            if r > best_r:
                best_r, best_c = r, c
    if best_c is None or best_r <= 0:
        return Cavity(None, None, "CAVITY_OPEN")
    diameter = 2 * best_r
    if diameter > D_MAX_MM:
        return Cavity(None, None, "CAVITY_OPEN")
    d_close = _seg_dist(best_c, j2d[3], close_pt)
    # 円が閉じる線を、半径の25%を超えて越えたら、指が回り込みきらないとみなす
    warning = "CAVITY_PARTIAL" if d_close < 0.75 * best_r else None
    center3d = origin + best_c[0] * d0 + best_c[1] * zaxis
    return Cavity(round(float(diameter), 1), center3d, warning)


def build(measurement: dict) -> HandModel:
    fingers = measurement["fingers"]
    palm = measurement["palm"]
    t = palm["palm_thickness_mm"]
    capsules: list[Capsule] = []
    cavities: dict[str, Cavity] = {}
    warnings: list[str] = []
    for f in FINGERS:
        fd = fingers[f]
        mcp = palm["mcp_positions_mm"][f]
        joints, d0, z = finger_chain(mcp, fd["abduction_deg"], fd["lengths_mm"], fd["flexion_deg"])
        for i, seg in enumerate(SEGMENTS):
            capsules.append(Capsule(f, seg, joints[i], joints[i + 1], fd["radii_mm"][i]))
        total = sum(fd["flexion_deg"][k] for k in ("mcp", "pip", "dip"))
        cav = cavity_for_finger(joints, d0, z, fd["radii_mm"], t, total)
        cavities[f] = cav
        if cav.warning and cav.warning not in warnings:
            warnings.append(cav.warning)
    return HandModel(capsules, cavities, warnings)


@dataclass
class GripFrame:
    origin: np.ndarray       # 握りの Z=0（小指側の端）
    rotation: np.ndarray     # 手の座標系 → 握りの座標系（行が x_g, y_g, z_g）
    axis_length: float       # |c_index − c_pinky|


def grip_frame(model: HandModel, end_margin: float) -> GripFrame | None:
    """握りの座標系（§8.4）。Z = 小指のすき間の中心 → 人差し指のすき間の中心。"""
    ci, cp = model.cavities["index"].center_mm, model.cavities["pinky"].center_mm
    if ci is None or cp is None:
        return None
    axis = ci - cp
    length = float(np.linalg.norm(axis))
    zg = axis / length
    palm_n = np.array([0.0, 0.0, 1.0])
    xg = palm_n - (palm_n @ zg) * zg           # 手のひら側を +x にする
    xg = xg / np.linalg.norm(xg)
    yg = np.cross(zg, xg)                       # 右手系
    origin = cp - end_margin * zg
    return GripFrame(origin, np.vstack([xg, yg, zg]), length)


def to_grip(frame: GripFrame, p: np.ndarray) -> np.ndarray:
    return frame.rotation @ (p - frame.origin)


def carve_report(capsules_g, d_bottom, d_top, length, bore_d, clearance, max_ratio=0.29, min_wall=3.0):
    """カプセルごとの実際のくり抜きの深さと残りの壁（parts-library.md §4.1）。"""
    worst_ratio_excess, min_wall_left, max_depth = -1e9, 1e9, 0.0
    problems = []
    for cap in capsules_g:
        p1, p2, r = np.array(cap[0:3]), np.array(cap[3:6]), cap[6]
        n = max(2, int(np.linalg.norm(p2 - p1)) + 1)
        for s in np.linspace(0, 1, n):
            p = p1 + s * (p2 - p1)
            if p[2] < 0 or p[2] > length:
                continue
            rho = math.hypot(p[0], p[1])
            r_grip = (d_bottom + (d_top - d_bottom) * p[2] / length) / 2
            inner = rho - r - clearance
            depth = r_grip - inner
            if depth > 0:
                max_depth = max(max_depth, depth)
                limit = max_ratio * (r + clearance)
                worst_ratio_excess = max(worst_ratio_excess, depth - limit)
                wall = inner - bore_d / 2
                min_wall_left = min(min_wall_left, wall)
    ok_overhang = worst_ratio_excess <= 0
    ok_wall = min_wall_left >= min_wall
    if not ok_overhang:
        problems.append("CARVE_TOO_DEEP")
    if not ok_wall:
        problems.append("WALL_TOO_THIN")
    return {"max_depth_mm": round(float(max_depth), 2),
            "min_wall_mm": None if min_wall_left == 1e9 else round(float(min_wall_left), 2),
            "ok": bool(ok_overhang and ok_wall), "problems": problems}


def baseline_fitted(model: HandModel, tool_d_max: float, clearance: float, end_margin: float = 12.0):
    """fitted の基準値。press_depth は、くり抜きの検査を満たす最大値（上限1.5）を探す。"""
    frame = grip_frame(model, end_margin)
    if frame is None:
        return None
    caps_g = [[*to_grip(frame, c.p1), *to_grip(frame, c.p2), c.radius] for c in model.capsules]
    caps_g = [[round(float(v), 2) for v in c] for c in caps_g]
    length = frame.axis_length + 2 * end_margin
    d_index = model.cavities["index"].diameter_mm
    d_pinky = model.cavities["pinky"].diameter_mm
    bore_d = tool_d_max + 0.5
    chosen, report = None, None
    for p in np.arange(1.5, 0.45, -0.1):
        d_top, d_bottom = d_index + 2 * p, d_pinky + 2 * p
        rep = carve_report(caps_g, d_bottom, d_top, length, bore_d, clearance)
        if rep["ok"]:
            chosen, report = round(float(p), 1), rep
            break
    if chosen is None:
        p = 0.5
        report = carve_report(caps_g, d_pinky + 1, d_index + 1, length, bore_d, clearance)
        chosen = None
    return {
        "press_depth_mm": chosen,
        "d_top_mm": round(float(d_index + 2 * (chosen or 0.5)), 1),
        "d_bottom_mm": round(float(d_pinky + 2 * (chosen or 0.5)), 1),
        "length_mm": round(float(length), 1),
        "end_margin_mm": end_margin,
        "capsules": caps_g,
        "carve": report,
        "frame": {"origin": frame.origin.round(2).tolist(), "rotation": frame.rotation.round(4).tolist()},
    }


def to_json(model: HandModel) -> dict:
    return {
        "frame": "hand",
        "capsules": [
            {"finger": c.finger, "segment": c.segment, "p1_mm": c.p1.round(2).tolist(),
             "p2_mm": c.p2.round(2).tolist(), "radius_mm": c.radius}
            for c in model.capsules
        ],
        "cavities": {
            f: {"diameter_mm": cav.diameter_mm,
                "center_mm": None if cav.center_mm is None else cav.center_mm.round(2).tolist(),
                "warning": cav.warning}
            for f, cav in model.cavities.items()
        },
        "warnings": model.warnings,
    }
