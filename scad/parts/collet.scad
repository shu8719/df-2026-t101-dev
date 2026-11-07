// コレット（握りの上端と一体）と締めナット。docs/parts-library.md §4.2・§4.3
// 入口のファイルで lib/common.scad と BOSL2（std.scad・threading.scad）を include してから include する

// コレット：Z=0 から上へ、ねじ（THREAD_LENGTH_MM）→ 割り片（COLLET_LENGTH_MM）
module collet(tool_d_max, slot_count=4) {
    r_in = tool_d_max / 2;
    r_out = r_in + COLLET_FINGER_WALL_MM;
    thread_d = thread_d_for(tool_d_max);
    sw = slot_width_for(slot_count);
    difference() {
        union() {
            // おねじ
            trapezoidal_threaded_rod(d = thread_d, l = THREAD_LENGTH_MM, pitch = THREAD_PITCH_MM,
                                     anchor = BOTTOM, $fa = 4, $fs = 0.5);
            // 割り片：根もとは r_out、先の9mmで外へ広がる（ナットの円すいがここを押す）
            translate([0, 0, THREAD_LENGTH_MM])
                rotate_extrude()
                    polygon([
                        [r_in, 0], [r_out, 0],
                        [r_out, COLLET_LENGTH_MM - COLLET_TAPER_LENGTH_MM],
                        [r_out + taper_flare(), COLLET_LENGTH_MM - 0.5],
                        [r_out + taper_flare() - 0.5, COLLET_LENGTH_MM],
                        [r_in, COLLET_LENGTH_MM]
                    ]);
        }
        // 道具を通す穴
        translate([0, 0, -1]) cylinder(r = r_in, h = THREAD_LENGTH_MM + COLLET_LENGTH_MM + 2);
        // 割り（ねじ部の上1mmから先まで）
        for (i = [0:slot_count - 1])
            rotate([0, 0, i * 360 / slot_count])
                translate([0, -sw / 2, THREAD_LENGTH_MM + 1])
                    cube([r_out + taper_flare() + 2, sw, COLLET_LENGTH_MM + 1]);
    }
}

// 締めナット：Z=0 が下端。下から、めねじ → 割り片の逃げ → 円すい → 上の縁
module collet_nut(tool_d_max, variant="wings", wing_span=50, edge_radius=2.0) {
    r_in = tool_d_max / 2;
    r_out = r_in + COLLET_FINGER_WALL_MM;
    thread_d = thread_d_for(tool_d_max);
    od = thread_d + 8;
    h = THREAD_LENGTH_MM + COLLET_LENGTH_MM + NUT_LIP_MM;
    er = max(edge_radius, MIN_EDGE_RADIUS_MM);
    cone_bottom_z = h - NUT_LIP_MM - COLLET_TAPER_LENGTH_MM;
    difference() {
        union() {
            cyl(d = od, h = h, rounding = er, anchor = BOTTOM, $fn = 64);
            if (variant == "wings") {
                wing_t = 7;
                wing_h = h * 0.75;
                for (s = [-1, 1])
                    hull() {
                        translate([0, 0, h - wing_h]) cyl(d = wing_t, h = wing_h, rounding = er, anchor = BOTTOM, $fn = 32);
                        translate([s * (wing_span / 2 - wing_t / 2), 0, h - wing_h])
                            cyl(d = wing_t, h = wing_h, rounding = er, anchor = BOTTOM, $fn = 32);
                    }
            }
        }
        // めねじ
        translate([0, 0, -0.01])
            trapezoidal_threaded_rod(d = thread_d, l = THREAD_LENGTH_MM + 0.02, pitch = THREAD_PITCH_MM,
                                     internal = true, $slop = THREAD_SLOP_MM, anchor = BOTTOM, $fa = 4, $fs = 0.5);
        // 割り片の逃げ（広がった先が通る太さ）
        translate([0, 0, THREAD_LENGTH_MM - 0.01])
            cylinder(r = r_out + taper_flare() + 0.6, h = cone_bottom_z - THREAD_LENGTH_MM + 0.02, $fn = 64);
        // 円すい：下が広く、上が細い（割り片の先を内側へ押す）
        translate([0, 0, cone_bottom_z])
            cylinder(r1 = r_out + taper_flare() + 0.6, r2 = r_out + 0.2, h = COLLET_TAPER_LENGTH_MM, $fn = 64);
        // 上の縁の穴（道具が通る）
        translate([0, 0, h - NUT_LIP_MM - 0.5]) cylinder(r = r_out + 0.2, h = NUT_LIP_MM + 1, $fn = 64);
        // ぎざぎざ
        if (variant == "knurl")
            for (i = [0:23]) rotate([0, 0, i * 15]) translate([od / 2, 0, -1]) cylinder(d = 2, h = h + 2, $fn = 12);
    }
}
