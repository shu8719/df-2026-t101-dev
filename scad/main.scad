// 入口。全引数の既定値をトップレベル変数で宣言する。生成APIは -D でここだけを上書きする。
// 変数名は <部品ID>_<引数名>（docs/parts-library.md §2）
include <vendor/BOSL2/std.scad>
include <vendor/BOSL2/threading.scad>
include <lib/common.scad>
include <parts/grip_body.scad>
include <parts/collet.scad>

// 全体
hand = "right";          // right / left
mode = "assembled";      // assembled / print
quality = "preview";     // preview / print

// 握り本体
grip_body_variant = "fitted";     // fitted / round / oval
grip_body_length_mm = 90;
grip_body_d_top_mm = 32;
grip_body_d_bottom_mm = 32;
grip_body_ovality = 1.0;
grip_body_finger_pos_mm = [14, 33, 51, 68];
grip_body_groove_enabled = [true, true, true, true];
grip_body_groove_width_mm = 16;
grip_body_groove_depth_mm = 2.0;
grip_body_bottom_flare_mm = 3;
grip_body_edge_radius_mm = 2.5;
grip_body_bore_through = true;
grip_body_capsules = [];          // [[x1,y1,z1,x2,y2,z2,r], ...]

// コレット
collet_tool_d_max_mm = 10.6;
collet_slot_count = 4;

// ナット
collet_nut_variant = "wings";     // wings / knurl
collet_nut_wing_span_mm = 50;
collet_nut_edge_radius_mm = 2.0;

$fn = fn_for(quality);
bore_d = collet_tool_d_max_mm + 0.5;
L = grip_body_length_mm;

module grip_with_collet() {
    grip_body(grip_body_variant, L, grip_body_d_top_mm, grip_body_d_bottom_mm, grip_body_ovality,
              grip_body_finger_pos_mm, grip_body_groove_enabled, grip_body_groove_width_mm,
              grip_body_groove_depth_mm, grip_body_bottom_flare_mm, grip_body_edge_radius_mm,
              grip_body_bore_through, bore_d, grip_body_capsules, hand);
    translate([0, 0, L - 0.01]) collet(collet_tool_d_max_mm, collet_slot_count);
}

module nut() {
    collet_nut(collet_tool_d_max_mm, collet_nut_variant, collet_nut_wing_span_mm, collet_nut_edge_radius_mm);
}

if (mode == "print") {
    // 立てて刷る：握り（コレットが上）と、ナットを横に並べる
    grip_with_collet();
    translate([max(grip_body_d_top_mm, grip_body_d_bottom_mm) / 2 + collet_nut_wing_span_mm / 2 + 10, 0, 0]) nut();
} else {
    // ナットを締めた状態
    grip_with_collet();
    translate([0, 0, L]) nut();
}
