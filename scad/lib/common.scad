// 固定値（AIは変えられない）。docs/parts-library.md §3 と scad/catalog.json の constants と同じ値にする。
NOZZLE_MM = 0.4;
MIN_WALL_MM = 2.0;
MIN_WALL_AROUND_BORE_MM = 3.0;
MIN_EDGE_RADIUS_MM = 1.5;
COLLET_FINGER_WALL_MM = 2.0;
THREAD_PITCH_MM = 3.0;
THREAD_SLOP_MM = 0.10;        // 仮。11/9の試し刷りで決める
THREAD_LENGTH_MM = 15;
COLLET_LENGTH_MM = 16;
COLLET_TAPER_DEG = 10;
COLLET_TAPER_LENGTH_MM = 9;
CLAMP_RANGE_MM = 3.0;         // 仮
CAPSULE_CLEARANCE_MM = 0.5;   // 仮。11/9の carve_test で決める
NUT_LIP_MM = 2;
FN_PREVIEW = 48;
FN_PRINT = 128;

function fn_for(quality) = quality == "print" ? FN_PRINT : FN_PREVIEW;

// ねじの外径（parts-library.md §4.2）
function thread_d_for(tool_d_max) = max(16, 2 * ceil((tool_d_max + 9) / 2));

// 割りの幅（parts-library.md §3）
function slot_width_for(slot_count) = PI * CLAMP_RANGE_MM / slot_count + 0.4;

// 割り片の先の広がり（片側）
function taper_flare() = COLLET_TAPER_LENGTH_MM * tan(COLLET_TAPER_DEG);
