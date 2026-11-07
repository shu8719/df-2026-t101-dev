// 握り本体。軸はZ。Z=0 が下端（小指側）、Z=length が上端（人差し指側）。
// docs/parts-library.md §4.1
// 入口のファイルで lib/common.scad を include してから include する

// 角を丸めた、先細りの回転体の断面（r, z）
function _grip_profile(r_bottom, r_top, length, er, flare, steps=8) =
    let(
        rb = r_bottom + flare,
        fh = flare * 1.5,
        // 下端の角（rb, 0）を丸める
        bottom_arc = [for (i = [0:steps]) let(a = -90 + 90 * i / steps)
                        [rb - er + er * cos(a), er + er * sin(a)]],
        // 上端の角（r_top, length）を丸める
        top_arc = [for (i = [0:steps]) let(a = 90 * i / steps)
                     [r_top - er + er * cos(a), length - er + er * sin(a)]]
    )
    concat([[0, 0]], bottom_arc,
           flare > 0 ? [[r_bottom, fh]] : [],
           top_arc, [[0, length]]);

module grip_solid(length, d_top, d_bottom, edge_radius, bottom_flare, ovality=1.0) {
    er = max(edge_radius, MIN_EDGE_RADIUS_MM);
    scale([1, ovality, 1])
        rotate_extrude()
            polygon(_grip_profile(d_bottom / 2, d_top / 2, length, er, bottom_flare));
}

// リング状のくぼみ（round / oval）
module ring_grooves(length, d_top, d_bottom, finger_pos, enabled, width, depth, ovality=1.0) {
    if (depth > 0) {
        R = (width * width / 4 + depth * depth) / (2 * depth);   // 円弧の半径
        for (i = [0:len(finger_pos) - 1]) if (enabled[i]) {
            z = length - finger_pos[i];
            r_here = d_bottom / 2 + (d_top - d_bottom) / 2 * (z / length);
            scale([1, ovality, 1])
                translate([0, 0, z])
                    rotate_extrude()
                        translate([r_here + R - depth, 0]) circle(r = R);
        }
    }
}

// 指のカプセル（くり抜く形）。caps = [[x1,y1,z1,x2,y2,z2,r], ...]（握りの座標系、mm）
module finger_capsules(caps, clearance=CAPSULE_CLEARANCE_MM) {
    for (c = caps)
        hull() {
            translate([c[0], c[1], c[2]]) sphere(r = c[6] + clearance);
            translate([c[3], c[4], c[5]]) sphere(r = c[6] + clearance);
        }
}

module grip_body(variant, length, d_top, d_bottom, ovality, finger_pos, groove_enabled,
                 groove_width, groove_depth, bottom_flare, edge_radius, bore_through,
                 bore_d, capsules, hand="right") {
    ov = variant == "oval" ? ovality : 1.0;
    difference() {
        grip_solid(length, d_top, d_bottom, edge_radius, bottom_flare, ov);
        if (variant == "fitted") {
            // 左手は右手の形を鏡像にしたもの（docs/measurement.md §8.1）
            mirror([hand == "left" ? 1 : 0, 0, 0]) finger_capsules(capsules);
        } else {
            ring_grooves(length, d_top, d_bottom, finger_pos, groove_enabled,
                         groove_width, groove_depth, ov);
        }
        // 柄を通す穴
        if (bore_through)
            translate([0, 0, -1]) cylinder(d = bore_d, h = length + 2);
        else
            translate([0, 0, length - 30]) cylinder(d = bore_d, h = 31);
    }
}
