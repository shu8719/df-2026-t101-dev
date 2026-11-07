// 確認用画像の描画専用。preview.stl を読み込み、道具の目安の棒と、手のカプセル（半透明）を添える。
// --preview で描く（色を出すため）。docs/generation-pipeline.md §6.3
stl_path = "preview.stl";
grip_color = "#3A7CA5";
tool_d = 10;
tool_top_z = 200;
hand = "right";
capsules = [];
clearance = 0;

color(grip_color) import(stl_path);
color("#D0342C") translate([0, 0, -40]) cylinder(d = tool_d, h = tool_top_z + 40, $fn = 24);
color([0.95, 0.75, 0.62, 0.45])
    mirror([hand == "left" ? 1 : 0, 0, 0])
        for (c = capsules)
            hull() {
                translate([c[0], c[1], c[2]]) sphere(r = c[6] + clearance, $fn = 24);
                translate([c[3], c[4], c[5]]) sphere(r = c[6] + clearance, $fn = 24);
            }
