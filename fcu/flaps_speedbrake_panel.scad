// Combined A320 SPEED BRAKE + FLAPS panel, ~160 x 100 mm, replacing
// MANTOGA's two 148.5 x 100 mm 3-layer acrylic panels (ma64 speedbrake,
// ma68 flaps) AND the two separate flaps lever arcs (ma68-09) plus their
// bent legend strips (ma68-18).
//
// Three 3 mm layers, like MANTOGA's acrylic stack:
//   base     z 0..3  blue
//   diffuser z 3..6  clear -- PLUS the flat legends, rising from it through
//                    the top layer to the top face (lit from below, same
//                    scheme as fcu_mk2 front_panel.scad's infill), PLUS an
//                    inner flaps arc (radius arc_r - arc_shell_t)
//   top      z 6..9  blue, with the flat legends cut out, PLUS an outer
//                    flaps arc: an arc_shell_t thick shell over the
//                    diffuser's arc, with the flap positions cut through
//                    it so the clear arc shows through
//   text_white       the outermost white_t (0.4 mm) of every legend, in
//                    white -- the diffuser stops short of it (same as
//                    front_panel.scad's main_panel_infill_front_slice())
//
// Frame: viewed from above, +Y = forward (top of the reference photos),
// z = 0 panel underside, z = 9 top face -- the same as MANTOGA's stack, so
// both mechanisms and the knobs mount exactly as designed.
//
// Layout (matches the real pedestal photos):
//   * SPEED BRAKE on the left. Its mechanism is MANTOGA's turned 180deg
//     about the vertical axis (lever right of the title, RET forward) --
//     MANTOGA's own engraving SVG is drawn in that orientation too.
//   * FLAPS on the right, mechanism as designed (lever left of the title).
//   The narrow (non-gear) sides of the two mechanisms face each other, so
//   the levers sit near the middle and each gear train sits outboard under
//   its title.
//
// part = "base" | "diffuser" | "text_white" | "top" -> printable bodies
//        "all"                                      -> stacked preview
//
// Dropped vs. the originals: the label light boxes (ma64-12 / ma68-17)
// and their 2 mm pin holes -- under the titles there's now a gear train,
// not free space -- and the arcs' LED pockets.

part = "all"; // [all, base, diffuser, text_white, top]

// ---------------- panel ----------------
panel_w   = 160;
panel_h   = 100;
layer_t   = 3;      // MANTOGA: 3 mm acrylic per layer
panel_t   = 3 * layer_t;
corner_r  = 1;

// lever slot centres (x); y = 0 for both
sb_x = -28;         // speedbrake slot
fl_x =  28;         // flaps slot
// min. spacing: 20.5 (sb frame, narrow side) + 20.5 (flaps frame) + gap
assert(fl_x - sb_x >= 44, "mechanism frames would collide (need >= 44 mm between slots)");
// gear-side frames sit at slot -/+ 41: keep them inside the side screw holes
assert(fl_x + 41 < panel_w / 2 - 6.05 - 2.85, "flaps frame runs into the side screw counterbores");

// ---------------- text (front_panel.scad settings = smallest printable) ----------------
font        = "Futura";
text_size   = 3.2;   // position legends -- do not go smaller
text_spacing= 1.1;
text_grow   = 0.15;  // offset(delta) like front_panel.scad's panel_text()
title_size  = 5.5;   // FLAPS / SPEED BRAKE (MANTOGA's SVG: 5.6)
line_w      = 1.0;   // speedbrake scale lines / ticks / box (0.6 too thin to print)
text_clearance = 0;  // extra gap around the legend cut-outs in the TOP layer
                     // only (0 = exact fit, as front_panel; raise if
                     // printing the layers separately and pressing together)

// ---------------- flaps arcs (measured from MANTOGA's ma68-09 STL) ----------------
// top surface = circle about the lever pivot axis (parallel to X):
// z(0) = 19.24, z(+-30) = 12.46  ->  centre z = -50.52, R = 69.76
arc_cz      = -50.52;
arc_r       = 69.76;  // outer (top layer) arc radius
arc_shell_t = layer_t; // top-layer shell thickness; diffuser arc = arc_r - this
arc_inner   = 6;      // arc inner face, from slot centre (= slot half-width)
arc_outer   = 19;     // arc outer face, from slot centre (13 mm wide arcs)
arc_len     = 76;     // footprint length (+-38)
// flap positions along the arc top (arc length from the middle, + = forward).
// EVENLY SPACED estimate: 0 / FULL near the arc ends as in the photo,
// 1/2/3 not visible there -- adjust to your detents.
flap_labels = [["0", 32], ["1", 16], ["2", 0], ["3", -16], ["FULL", -32]];

// ---------------- holes (all from MANTOGA's DXFs) ----------------
// frame screws: 7.5 counterbore through top+diffuser, 4.5 through base
frame_cb_d = 7.5;  frame_cb_depth = 2 * layer_t;  frame_hole_d = 4.5;
// panel screws: 5.7 counterbore through top, 3.5 through diffuser+base
panel_cb_d = 5.7;  panel_cb_depth = layer_t;      panel_hole_d = 3.5;
// base-only holes (pedestal mounting)
blind_d = 4.5;     blind_depth = layer_t;
edge_in = 6.05;    // hole centre from the panel's side edges (74.25 - 68.2)

$fn = 48;
eps = 0.01;

// ======================================================================
// geometry helpers
// ======================================================================
module rounded_rect(w, h, r) {
  offset(r) offset(-r) square([w, h], center = true);
}
module stadium(w, len) { // slot with full-round ends, centred
  hull() for (s = [-1, 1]) translate([0, s * (len - w) / 2]) circle(d = w);
}
module legend_text(s, size = text_size, halign = "center") {
  offset(delta = text_grow)
    text(s, size = size, font = font, halign = halign, valign = "center", spacing = text_spacing);
}
module seg(p1, p2, w = line_w) {
  hull() { translate(p1) circle(d = w, $fn = 12); translate(p2) circle(d = w, $fn = 12); }
}
module square_from(b) { translate([b[0], b[1]]) square([b[2] - b[0], b[3] - b[1]]); }
module slab(z0, z1) { translate([-500, -500, z0]) cube([1000, 1000, z1 - z0]); }

// ======================================================================
// slots through the plate (2D, panel frame)
// ======================================================================
// speedbrake: 12 x 80 stadium (ma64-01/02/03)
module sb_slot_2d() { translate([sb_x, 0]) stadium(12, 80); }
// flaps lever slot: 12 x 88 stadium (ma68-01/02/03; the rest of MANTOGA's
// 38 x 76 pocket is now solid arc)
module fl_slot_2d() { translate([fl_x, 0]) stadium(12, 88); }

// ======================================================================
// flaps arcs (3D) -- one each side of the flaps slot, two concentric
// radii: arc_r (top layer, outer) and arc_r - arc_shell_t (diffuser, inner)
// ======================================================================
module arc_profile_yz(r) { // in (y, z): under the pivot circle, z >= 0, |y| <= len/2
  intersection() {
    translate([0, arc_cz]) circle(r = r, $fn = 720);
    translate([-arc_len / 2, 0]) square([arc_len, arc_r]);
  }
}
module arc_3d(x0, x1, r) { // solid between x0..x1 (absolute)
  translate([x0, 0, 0]) rotate([90, 0, 90]) linear_extrude(x1 - x0) arc_profile_yz(r);
}
// inset narrows each arc from both sides -- used for the diffuser's inner
// arc so the top layer forms side walls around it (arc fully enclosed in
// blue above the panel; the ends are already closed by the outer shell)
arc_side_wall = 1.2;  // 13 -> 10.6 mm inner arc; widest label (FULL) is 10.1
module arcs_3d(r = arc_r, inset = 0) {
  arc_3d(fl_x - arc_outer + inset, fl_x - arc_inner - inset, r);
  arc_3d(fl_x + arc_inner + inset, fl_x + arc_outer - inset, r);
}
// flap positions: each label tangent to the arc at its angle about the
// pivot axis, cut radially through the top-layer shell down to the
// diffuser arc (and a little past it so the cut is clean)
module arc_text_3d(grow = 0) {
  for (xc = [fl_x - (arc_inner + arc_outer) / 2, fl_x + (arc_inner + arc_outer) / 2])
    for (l = flap_labels)
      translate([xc, 0, arc_cz])
        rotate([-(l[1] / arc_r) * 180 / PI, 0, 0])
          translate([0, 0, arc_r - arc_shell_t - 0.5])
            linear_extrude(arc_shell_t + 1.5) offset(delta = grow) legend_text(l[0]);
}

// ======================================================================
// holes
// ======================================================================
// [x, y] relative to each slot, in the PANEL frame
// flaps (as designed): DXF (-57.5|-26.5, +-45) relative to slot x=-42
fl_frame_holes = [[-15.5, 45], [15.5, 45], [-15.5, -45], [15.5, -45]];
// speedbrake (DXF (-57.5,45), (-26.5,45), (-7.3,-45)) turned 180deg
sb_frame_holes = [[15.5, -45], [-15.5, -45], [-34.7, 45]];

module frame_hole() {
  translate([0, 0, -eps]) cylinder(d = frame_hole_d, h = panel_t + 2 * eps);
  translate([0, 0, panel_t - frame_cb_depth]) cylinder(d = frame_cb_d, h = frame_cb_depth + eps);
}
module holes_3d() {
  for (h = fl_frame_holes) translate([fl_x + h[0], h[1]]) frame_hole();
  for (h = sb_frame_holes) translate([sb_x + h[0], h[1]]) frame_hole();
  // panel screws (counterbored from the top) + base-only holes
  for (sx = [-1, 1]) {
    x = sx * (panel_w / 2 - edge_in);
    for (y = [-31, 22]) translate([x, y]) {
      translate([0, 0, -eps]) cylinder(d = panel_hole_d, h = panel_t + 2 * eps);
      translate([0, 0, panel_t - panel_cb_depth]) cylinder(d = panel_cb_d, h = panel_cb_depth + eps);
    }
    for (y = [-44, 35]) translate([x, y, -eps]) cylinder(d = blind_d, h = blind_depth + eps);
  }
}

// ======================================================================
// flat legends on the top face (2D, panel frame)
// ======================================================================
// Speedbrake scale, from MANTOGA's "SPEED BRAKE Panel Master ma14.svg"
// (positions relative to the slot) and the reference photo: a vertical
// line each side of the slot, RET / 1/2 / FULL outboard with major ticks,
// minor ticks between, arrows from RET up to a boxed GND SPLRS ARMED.
sb_line_dx = 9;                 // scale line distance from slot centre
sb_major   = [["RET", 31.8], ["1/2", 0], ["FULL", -34.6]];
sb_minor   = [15.9, -17.3];
sb_arrow_tip = 39.8;
// widened from the SVG's 43.2 x 5.5 so the 3.2 mm text fits inside;
// outer edge of the box line kept >= 2 mm from the panel edge
sb_box     = [-27.5, 40.8, 21.7, 47.4]; // x0, y0, x1, y1 (relative to slot x)
module sb_scale_2d() {
  translate([sb_x, 0]) {
    for (s = [-1, 1]) {
      lx = s * sb_line_dx;
      seg([lx, sb_major[2][1]], [lx, sb_arrow_tip - 2]);
      translate([lx, sb_arrow_tip]) polygon([[0, 0], [-1.5, -3], [1.5, -3]]); // arrow head
      for (m = sb_major) {
        seg([lx, m[1]], [lx + s * 2.2, m[1]]);
        translate([lx + s * 3.4, m[1]]) legend_text(m[0], halign = s < 0 ? "right" : "left");
      }
      for (y = sb_minor) seg([lx, y], [lx - s * 1.8, y]);
    }
    difference() { // GND SPLRS ARMED box
      offset(line_w / 2) square_from(sb_box);
      offset(-line_w / 2) square_from(sb_box);
    }
    translate([(sb_box[0] + sb_box[2]) / 2, (sb_box[1] + sb_box[3]) / 2]) legend_text("GND SPLRS ARMED");
  }
}

// titles: over each mechanism's outboard (gear) side, like the photos
sb_title_x = -63.5;
fl_title_x =  63;
module titles_2d() {
  translate([sb_title_x,  title_size * 0.65]) legend_text("SPEED", title_size);
  translate([sb_title_x, -title_size * 0.65]) legend_text("BRAKE", title_size);
  translate([fl_title_x, 0]) legend_text("FLAPS", title_size);
}

module flat_legends_2d() { sb_scale_2d(); titles_2d(); }

// ======================================================================
// layers
// ======================================================================
module plate_whole() { // everything, all layers together
  difference() {
    union() {
      linear_extrude(panel_t) rounded_rect(panel_w, panel_h, corner_r);
      arcs_3d();
    }
    translate([0, 0, -eps]) linear_extrude(arc_r) { sb_slot_2d(); fl_slot_2d(); }
    holes_3d();
  }
}
// diffuser material that rises through the top layer
module diffuser_rise_3d(grow = 0) {
  translate([0, 0, 2 * layer_t - eps]) linear_extrude(100) offset(delta = grow) flat_legends_2d();
  arcs_3d(arc_r - arc_shell_t, arc_side_wall);   // inner arc, walled in by the top layer
  arc_text_3d(grow);              // flap positions through the shell
}

// white front slice of every legend, like front_panel.scad's
// main_panel_infill_front_slice(): the outermost white_t of the letters
white_t = 0.4;
module white_zone_3d() {
  // flat legends: top white_t below the top face
  intersection() {
    slab(panel_t - white_t, panel_t + 1);
    translate([0, 0, 2 * layer_t]) linear_extrude(100) flat_legends_2d();
  }
  // flap positions: outer white_t radially, under the curved arc surface
  intersection() {
    arc_text_3d();
    difference() { arcs_3d(arc_r + 1); arcs_3d(arc_r - white_t); }
  }
}

// LED strip channels, cut right through the base so the strip lights the
// diffuser directly. Placed in the bands where NOTHING of either mechanism
// touches the panel underside (measured from MANTOGA's parts as placed):
//   speedbrake slot light box  x -57.5 .. -7.5  (full length)
//   speedbrake frame bracket   x -67.7 .. -57.7 (y 40 .. 50 only)
//   flaps frames + blocker     x   7.5 .. 48.5
// [x centre, y0, y1]; left one stops short of the frame bracket.
led_w        = 10.5;   // channel width (10 mm strip + clearance)
led_channels = [
  [-64, -41, 33],      // left, under SPEED BRAKE (74 mm)
  [  0, -41, 41],      // middle, between the two mechanisms (82 mm)
  [ 63, -41, 41],      // right, under FLAPS (82 mm)
];
module led_channels_2d() {
  for (c = led_channels) translate([c[0] - led_w / 2, c[1]]) square([led_w, c[2] - c[1]]);
}

module base() {
  difference() {
    intersection() { plate_whole(); slab(-1, layer_t); }
    translate([0, 0, -1]) linear_extrude(layer_t + 2) led_channels_2d();
  }
}
// blue rim around the diffuser at its own level (z 3..6): diffuser_rim
// wide along the panel's outer edge and around both lever slots, so no
// clear edge shows anywhere. It belongs to the TOP layer (a skirt hanging
// down from it); the diffuser shrinks by the same amount.
diffuser_rim = 2;
module rim_2d() {
  difference() {
    square([panel_w + 10, panel_h + 10], center = true);
    offset(delta = -diffuser_rim) rounded_rect(panel_w, panel_h, corner_r);
  }
  offset(delta = diffuser_rim) { sb_slot_2d(); fl_slot_2d(); }
}
module rim_3d() { translate([0, 0, layer_t]) linear_extrude(layer_t) rim_2d(); }

module diffuser() { // its own 3 mm layer + legends (minus the white slice) + inner arc
  difference() {
    intersection() {
      plate_whole();
      slab(layer_t, 100);
      union() { slab(layer_t - 1, 2 * layer_t); diffuser_rise_3d(); }
    }
    white_zone_3d();
    rim_3d();
  }
}
module text_white() { intersection() { plate_whole(); white_zone_3d(); } }
module top() { // incl. the outer arc shell and the rim skirt round the diffuser
  union() {
    difference() {
      intersection() { plate_whole(); slab(2 * layer_t, 100); }
      diffuser_rise_3d(text_clearance);
    }
    intersection() { plate_whole(); rim_3d(); }
  }
}

// ======================================================================
if (part == "base") base();
else if (part == "diffuser") diffuser();
else if (part == "text_white") text_white();
else if (part == "top") top();
else {
  color("RoyalBlue") base();
  color("LightCyan", 0.85) diffuser();
  color("White") text_white();
  color("RoyalBlue") top();
}
