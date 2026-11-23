// 試作：万力式の取り付け具（2026-11-23、feat/attachment-variants）。C字クリップと比べる試し刷り用で、生成APIからはまだ呼ばない。
// しくみ：受け具の穴の手の側（−X）を 90度の V 字にし、外側（+X）から刷ったねじを回して、道具の柄を V 字へ押し付ける。
//   V 字に押し付けるので、太さの違う道具（VISE_TOOL_D_MIN_MM〜VISE_TOOL_D_MAX_MM）を 1 つの受け具で挟める。
//   ねじのつまみは T 字で、こぶしの外側（+X）に出る（介護する人が回しやすい側）。
// 部品は 2 つ：受け具（舌・腕と一体）と、ねじ（つまみ付き）。ねじは BOSL2 の台形ねじ。すき間は試し刷りで決める（要確認）。

VISE_H_MM = 20;                // 受け具の高さ（道具の軸の向き）。C字の輪の高さと同じ
VISE_WALL_MM = 2.5;            // 穴のまわりの肉
VISE_SCREW_D_MM = 12;
VISE_SCREW_PITCH_MM = 3.0;
VISE_SCREW_SLOP_MM = 0.10;     // 仮。BOSL2 の $slop
VISE_BOSS_LEN_MM = 10;         // めねじのかかる長さ（穴の縁から外へ）
VISE_KNOB_SPAN_MM = 32;        // T 字のつまみの長さ
VISE_KNOB_T_MM = 9;            // つまみの太さ
VISE_LAT_MM = 26;              // 受け具の中心を親指側へ出す量。手の側の端が C字の輪とほぼ同じ所に来るよう離した（要確認）
VISE_DOWN_MM = 6;
VISE_FWD_MM = 5;

function vise_r(dmax) = dmax / 2 + 0.5;                     // 穴の丸い側の半径（いちばん太い道具＋0.5）
function vise_apex_x(dmax) = -vise_r(dmax) * sqrt(2);         // V 字の頂点（90度の V が半径 vise_r の円に接する）
function vise_tool_x(d, dmax) = vise_apex_x(dmax) + d / sqrt(2);   // 太さ d の道具が V 字に収まったときの中心
function vise_boss_end(dmax) = vise_r(dmax) + VISE_BOSS_LEN_MM;
function vise_outer_min_x(dmax) = vise_apex_x(dmax) - VISE_WALL_MM - 0.3;
function vise_center() = holder_center(VISE_LAT_MM, VISE_DOWN_MM, VISE_FWD_MM);
// ねじのねじ山の長さ：いちばん細い道具に届き、つまみが受け具から 3mm 離れる
function vise_screw_len(dmin, dmax) = vise_boss_end(dmax) - (vise_tool_x(dmin, dmax) + dmin / 2) + 3;

module vise_cavity_2d(dmax) {
  hull() {
    circle(r = vise_r(dmax));
    translate([vise_apex_x(dmax), 0]) circle(r = 0.3, $fn = 12);
  }
}

// 受け具の本体（局所座標）。穴とめねじはあとで抜く
module vise_body_local(dmax, quality) {
  $fn = fn_for(quality);
  translate([0, 0, -VISE_H_MM / 2]) linear_extrude(height = VISE_H_MM) offset(r = VISE_WALL_MM) vise_cavity_2d(dmax);
  // ねじのボス（+X）
  rotate([0, 90, 0]) cylinder(d = VISE_SCREW_D_MM + 6, h = vise_boss_end(dmax));
}

module vise_cuts_local(dmax, quality) {
  $fn = fn_for(quality);
  translate([0, 0, -VISE_H_MM / 2 - 1]) linear_extrude(height = VISE_H_MM + 2) vise_cavity_2d(dmax);
  // めねじ（X の向き）
  translate([vise_r(dmax) * 0.5, 0, 0]) rotate([0, 90, 0])
    trapezoidal_threaded_rod(d = VISE_SCREW_D_MM, l = vise_boss_end(dmax) - vise_r(dmax) * 0.5 + 0.02,
                             pitch = VISE_SCREW_PITCH_MM, internal = true, $slop = VISE_SCREW_SLOP_MM,
                             bevel1 = false, bevel2 = true, anchor = BOTTOM, $fa = 4, $fs = 0.5);
}

// レールの座標に組んだ形（受け具だけ）
module vise_holder_rail(dmax = 12, tilt = 70, quality = "preview") {
  c = vise_center();
  M = holder_matrix(c, tilt);
  difference() {
    union() {
      holder_tongue_and_arm(c, tilt, vise_outer_min_x(dmax) + 0.3, -VISE_H_MM * 0.4, VISE_H_MM * 0.4, quality);
      multmatrix(M) vise_body_local(dmax, quality);
    }
    multmatrix(M) vise_cuts_local(dmax, quality);
  }
}

// 刷る向き：道具の軸を立てる（めねじが横向きになる。ピッチ 3mm の台形ねじなら横でも刷れる見込み：要確認）
module vise_holder_print(dmax = 12, tilt = 70, quality = "print") {
  holder_print(vise_center(), tilt, -VISE_H_MM / 2) vise_holder_rail(dmax, tilt, quality);
}

// ねじ（Z=0 が下端。つまみを下にして立てて刷る）
module vise_screw(dmin = 6, dmax = 12, quality = "print") {
  $fn = fn_for(quality);
  L = vise_screw_len(dmin, dmax);
  // T 字のつまみ
  hull() for (s = [-1, 1]) translate([s * (VISE_KNOB_SPAN_MM / 2 - VISE_KNOB_T_MM / 2), 0, 0])
    cylinder(d = VISE_KNOB_T_MM, h = VISE_KNOB_T_MM);
  cylinder(d = VISE_SCREW_D_MM + 4, h = VISE_KNOB_T_MM);
  translate([0, 0, VISE_KNOB_T_MM - 0.01])
    trapezoidal_threaded_rod(d = VISE_SCREW_D_MM, l = L, pitch = VISE_SCREW_PITCH_MM,
                             bevel1 = false, bevel2 = true, anchor = BOTTOM, $fa = 4, $fs = 0.5);
}

// assembled の表示用：ねじを、太さ d の道具に当たるところまで入れた位置（局所座標）
module vise_screw_at(d, dmin = 6, dmax = 12, quality = "preview") {
  tip = vise_tool_x(d, dmax) + d / 2;
  L = vise_screw_len(dmin, dmax);
  translate([tip + L + VISE_KNOB_T_MM, 0, 0]) rotate([0, -90, 0]) vise_screw(dmin, dmax, quality);
}
