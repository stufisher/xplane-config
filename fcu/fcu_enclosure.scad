// printed as three separate parts, split at the panel seams
part = "all"; // [all, left, main, right]

panel_width   = 260;  // must match front_panel.scad main_panel_width
panel_height  = 80;   // must match front_panel.scad main_panel_height
side_panel_width = 100;  // must match front_panel.scad side_panel_width
panel_depth   = 3;    // must match front_panel.scad panel_depth
corner_inset  = 4;    // must match front_panel.scad panel()'s `inset`

wall          = 3;    // enclosure side/back wall thickness
depth         = 144;   // interior clearance behind the panel for encoders/
                       // PCBs/wiring -- 150mm overall front-to-back
                       // (panel_depth + depth + wall)
base_tilt     = 4;   // bottom wall slopes up toward the back by this angle (deg),
                       // pivoting on the front-bottom edge, so the box sits with
                       // the panel leaning back
top_tilt      = 2;   // top wall slopes down toward the back by this angle (deg),
                       // pivoting on the front-top edge (0 = flat; -base_tilt =
                       // parallel to the base, i.e. level when sat on the desk)

// infill (light disperser) stack behind the panel, from front_panel.scad's
// main_panel(infill=true): disperser plate + panel_edge() ring behind it,
// plus the mount_bosses() blocks / korry tabs hanging off the disperser's back face
disperser_panel_depth = 2;  // must match front_panel.scad disperser_panel_depth
infill_edge_depth     = 3;  // front_panel.scad panel_edge()'s default depth (= panel_depth)
infill_boss_depth     = 5;  // front_panel.scad mount_bosses() rotary_mount_depth default /
                             // korry tab_depth -- deepest thing behind any panel
infill_x0             = 2;  // main infill footprint x:[2, 258]
infill_y0             = 2;
infill_w              = panel_width - 4;
infill_h              = 50 - 3;  // front_panel.scad panel_height=50-3 -> y:[2, 49]
infill_depth          = disperser_panel_depth + max(infill_edge_depth, infill_boss_depth);

// mating face offsets (box front face -> block face), so each screw clamps
// panel + whatever infill is behind it straight onto the block, no air gap
top_mount_offset    = panel_depth;  // main panel top corners: no infill there
                                    // (main infill stops at y=49), flush behind the panel
infill_mount_offset = panel_depth + disperser_panel_depth;
                                    // side panels (full-panel infill, its holes line up
                                    // with the panel's) and main bottom corners: flush
                                    // behind the 2mm disperser plate, with a relief for
                                    // the main infill's edge ring (infill_ring_relief())

// corner mount screw holes: M3 self-tapped straight into the plastic, through
// an oval so the thread cuts into the two narrow sides and the wide sides give
// the displaced plastic somewhere to go (less splitting, easier to drive).
// Narrow axis along x, so the thinnest wall faces the side walls/displays.
tap_minor     = 2.8;  // across x: thread bites here (not too tight, so PLA doesn't split)
tap_major     = 3.4;  // across y: M3 clearance, so the screw only cuts the narrow sides
tap_depth     = 7;    // < block_h so it's blind; M3x10-12 through panel+infill
block_size    = 9;    // corner mount block width -- must be > 2*corner_inset so it
                       // genuinely overlaps the side walls (not just flush, which
                       // produces non-manifold geometry)
block_h       = 8;    // block height below its mating face, before the 45deg taper

// connections between the three parts: a rib along the inside of the top,
// back and bottom walls at each seam, bolted face-to-face with M3 + nut
rib_t         = 4;    // rib thickness on each side of the seam
rib_h         = 10;   // rib height off the walls
rib_hole_d    = 3.4;  // M3 clearance
rib_front_offset = panel_depth + infill_depth;  // ribs stop behind the deepest infill
                                                // (edge ring / korry tabs / bosses)

// cable pass-through in the main part's back wall, sized for a USB-A plug
// (~12 x 4.5mm, ~16 x 8mm overmould) to fit through
usb_w         = 18;
usb_h         = 10;
usb_r         = 2;    // corner radius
usb_x         = panel_width/2;  // centre, in the main part
usb_floor_gap = 2;    // cutout's bottom edge -> top of the tilted floor at the back

block_overlap = block_size/2 - corner_inset;  // how far each block runs into the side walls
block_reach   = block_size - block_overlap;   // cavity corner -> block's far edges

global_fn = 32;

box_x0  = -side_panel_width;
box_x1  = panel_width + side_panel_width;
seams   = [0, panel_width];
outer_h = panel_height + 2*wall;
front_z = panel_depth/2;  // box front face, flush with the panel's front face
back_z  = -(panel_depth/2 + depth);  // inner face of the back wall

// top of the tilted floor where it meets the back wall's outer face (its
// highest point there), so the USB cutout sits right at the bottom
back_floor_y = -wall + (front_z - (back_z - wall))*tan(base_tilt) + wall/cos(base_tilt);
usb_y = back_floor_y + usb_floor_gap + usb_h/2;

// corner_positions: [x, y, mating face offset back from front_z, outer corner]
panel_xs = [  // [hole x, outer corner (fused to a side wall)]
  [box_x0 + corner_inset, true],  [-corner_inset, false],                 // side_left
  [corner_inset, false],          [panel_width - corner_inset, false],    // main
  [panel_width + corner_inset, false], [box_x1 - corner_inset, true],     // side_right
];
// panel corner holes whose M3 screw line runs straight through a korry
// housing or its infill clip tab (front_panel.scad layout), so no screw can
// go in there whatever the enclosure does -- no block at all
dropped_corners = [
  [-corner_inset,              corner_inset],                 // side_left bottom-right: EFIS pushbutton [-13,14] housing
  [box_x1 - corner_inset,      corner_inset],                 // side_right bottom-right: ECAM FAN [346,12] housing
  [panel_width + corner_inset, panel_height - corner_inset],  // side_right top-left: ECAM [272.5,70] clip tab
  [box_x1 - corner_inset,      panel_height - corner_inset],  // side_right top-right: ECAM [347.5,70] clip tab
];
function is_dropped(x, y) =
  len([for (d = dropped_corners) if (abs(d[0] - x) < 0.01 && abs(d[1] - y) < 0.01) 1]) > 0;
function is_main(x) = x > 0 && x < panel_width;
// main panel top corners: the display boards / rear_mount() bars come within
// ~2.5mm of the hole, so those blocks are cut down to a triangle in the
// corner (tri_L = leg length along the wall/seam) clear of the displays
tri_L = 11.5;  // triangle leg, from the panel corner (~1mm wall around the oval)
corner_positions = [  // [x, y, offset, outer, triangle leg (0 = square)]
  for (px = panel_xs, y = [corner_inset, panel_height - corner_inset])
    if (!is_dropped(px[0], y))
      let (main_top = is_main(px[0]) && y > panel_height/2)
      [px[0], y,
       main_top ? top_mount_offset : infill_mount_offset,
       px[1],
       main_top ? tri_L : 0]
];

// the nearest panel corner to a hole at (x, y)
function nearest(v, xs) = [for (a = xs) if (abs(a - v) == min([for (b = xs) abs(b - v)])) a][0];
function panel_corner(x, y) = [nearest(x, [box_x0, 0, panel_width, box_x1]),
                               y < panel_height/2 ? 0 : panel_height];

// the 8 display boards behind the main panel's windows, plus front_panel.scad's
// rear_mount() bars (inside the same footprint) -- must match front_panel.scad's
// front_windows(3.5, 49) / rear_mount(3.5, 49), board_w=33, board_h=28,
// slot_y(i) = 3 + cumulative gap_holes*2.54
display_x0    = 3.5 + 3;                      // first board's left edge
display_x1    = 3.5 + 3 + 84*2.54 + 33;       // last board's right edge (slot_y(7) + board_w)
display_y0    = 49;
display_y1    = 49 + 28;
display_depth = 40;  // how far back the board stack reaches -- a guess, generous
module display_keepout() {
  c = korry_clear;
  translate([display_x0 - c, display_y0 - c, front_z - panel_depth - display_depth])
    cube([display_x1 - display_x0 + 2*c, display_y1 - display_y0 + 2*c, display_depth + 1]);
}

// small screwless triangular pads backing up the side_right panel's corners
// where no screw can go (see dropped_corners): face flush behind the side
// infill, legs sized to clear the korry housings/tabs there
// [corner x, corner y, leg, outer corner (both sides are walls)]
corner_pads = [
  [box_x1,      0,            6.5, true],   // bottom-right, next to ECAM FAN
  [panel_width, panel_height, 8.5, false],  // top-left (seam side), next to ECAM [272.5,70]
  [box_x1,      panel_height, 8.5, true],   // top-right, next to ECAM [347.5,70]
];
pad_h = 6;  // pad depth below its face, before the 45deg taper

// korry positions/sizes, for the keep-outs cut out of the corner blocks --
// must match front_panel.scad's efis()/ecam()/fcu()/baro()/rmp() calls
// (same list as scripts/gen_assembly_viewer.mjs)
korry_efis_pos = [
  [180, 11], [172, 27], [188, 27], [147.5, 11], [212.5, 11], [241, 11],   // fcu()
  [80, 11], [96, 11], [55, 11],                                          // baro(), rmp()
  [-20, 70], [-35, 70], [-50, 70], [-65, 70], [-80, 70],                 // efis()
  [347.5, 70], [332.5, 70], [317.5, 70], [302.5, 70], [287.5, 70], [272.5, 70],  // ecam()
  [347.5, 57], [332.5, 57], [317.5, 57], [302.5, 57], [287.5, 57], [272.5, 57],
];
korry_button_pos = [
  [16, 14], [36, 14],                  // fcu()
  [-33, 14], [-13, 14],                // efis()
  [306, 12], [326, 12], [346, 12],     // ecam()
];
// [housing half x, housing half y, housing back z, infill tab inner x
//  (front_panel.scad's half_width), infill tab half length (half_width*1.5/2)]
korry_efis_dims   = [6.8,  6.0,  -17.84, 8.5*0.8,          8.5*0.8*0.75];
korry_button_dims = [9.16, 9.16, -26.78, 11.95*0.8 - 0.3,  (11.95*0.8 - 0.3)*0.75];
korry_tab_depth   = 5;    // front_panel.scad korry tab_depth, hanging off the disperser's back
korry_clear       = 0.3;  // keep-out clearance, each side

// x range of the part a given x falls in, pulled back seam_gap from each
// seam -- a block face lying exactly on the seam plane leaves a
// zero-thickness (non-manifold) face in the neighbouring part's clip
seam_gap = 0.01;
function part_x0(x) = x < 0 ? box_x0 - wall : (x < panel_width ? seam_gap : panel_width + seam_gap);
function part_x1(x) = x < 0 ? -seam_gap : (x < panel_width ? panel_width - seam_gap : box_x1 + wall);

big = 1000;

// underside tapers at 45deg down into the walls, so it prints without
// supports with the back wall on the bed: into the cavity corner for an
// outer corner, into the top/bottom wall for one next to a seam. Clipped
// to its own part so it doesn't straddle the seam.
module corner_block(x, y, offset, outer, tri = 0) {
  bottom = front_z - offset - block_h;
  cx = x < 0 ? box_x0 - block_overlap : box_x1;
  cy = y < panel_height/2 ? -block_overlap : panel_height;
  pc = panel_corner(x, y);
  difference() {
    intersection() {
      hull() {
        translate([x - block_size/2, y - block_size/2, bottom])
          cube([block_size, block_size, block_h]);
        if (outer)
          translate([cx, cy, bottom - block_reach])
            cube([block_overlap, block_overlap, 0.01]);
        else
          translate([x - block_size/2, cy, bottom - block_reach])
            cube([block_size, block_overlap, 0.01]);
      }
      translate([part_x0(x), -big/2, -big/2])
        cube([part_x1(x) - part_x0(x), big, big]);
      // triangle in the corner: |dx| + |dy| <= tri from the panel corner
      if (tri > 0)
        translate([pc[0], pc[1], 0]) rotate([0, 0, 45])
          cube([tri*sqrt(2), tri*sqrt(2), big], center = true);
    }
    korry_keepouts_near(x, y);
    if (is_main(x)) {
      infill_ring_relief();
      infill_boss_keepouts();
      display_keepout();
    }
  }
}

// screwless triangular pad in a cavity corner (cx, cy), legs `leg` along the
// wall(s), face at the side infill's back; its underside tapers at 45deg
// into the corner edge (outer) or into the top/bottom wall (seam side).
// Grown 0.5mm into the walls so it fuses with them.
module corner_pad(cx, cy, leg, outer) {
  // into the box, x: away from an outer side wall, or into the side panel
  // (away from the main panel) at a seam
  ux = outer ? (cx > (box_x0 + box_x1)/2 ? -1 : 1) : (cx > panel_width/2 ? 1 : -1);
  uy = cy > panel_height/2 ? -1 : 1;        // into the box, y
  g  = 0.5;
  gx = outer ? g : 0;
  face = front_z - infill_mount_offset;
  tri_pts = [[cx - ux*gx, cy - uy*g], [cx + ux*leg, cy - uy*g], [cx - ux*gx, cy + uy*leg]];
  difference() {
    intersection() {
      hull() {
        translate([0, 0, face - pad_h])
          linear_extrude(height = pad_h) polygon(tri_pts);
        if (outer)
          translate([cx - ux*gx - (ux < 0 ? 0 : 0.01), cy - uy*g - (uy < 0 ? 0 : 0.01), face - pad_h - leg])
            cube([0.01, 0.01, 0.01]);
        else
          translate([0, 0, face - pad_h - leg])
            linear_extrude(height = 0.01)
              polygon([[cx, cy - uy*g], [cx + ux*leg, cy - uy*g], [cx + ux*leg, cy], [cx, cy]]);
      }
      // keep it inside its own part (seam side)
      translate([part_x0(cx + ux), -big/2, -big/2])
        cube([part_x1(cx + ux) - part_x0(cx + ux), big, big]);
    }
    korry_keepouts_near(cx, cy);
  }
}

disperser_back_z = -(panel_depth/2 + disperser_panel_depth);

// main infill mount_bosses() blocks that land inside a main bottom corner
// block's footprint (6.5mm square, rotary_mount_depth=5 behind the
// disperser) -- must match front_panel.scad's fcu() calls:
//   mount_bosses(center - korry_left + 18.5, 11, spacing=32)  -> x = 34.5 - 32
//   mount_bosses(center + outer2 - right_button_offset, 11, spacing=25) -> x = 226.4 + 25
infill_boss_pos  = [[2.5, 11], [251.4, 11]];
infill_boss_size = 6.5;
module infill_boss_keepouts() {
  c = korry_clear;
  for (p = infill_boss_pos)
    translate([p[0], p[1], disperser_back_z - infill_boss_depth/2])
      cube([infill_boss_size + 2*c, infill_boss_size + 2*c, infill_boss_depth + 2*c], center = true);
}

// every korry, for the whole box: trims the seam ribs and the tilted floor
// where a housing's back corner reaches them
module korry_keepouts_all() {
  for (p = korry_efis_pos)   korry_keepout(p, korry_efis_dims);
  for (p = korry_button_pos) korry_keepout(p, korry_button_dims);
}

// one korry's housing + its two infill clip tabs, grown by korry_clear;
// runs forward past the panel's back face so it cuts clean through a block
module korry_keepout(p, d) {
  c = korry_clear;
  translate([p[0] - d[0] - c, p[1] - d[1] - c, d[2] - c])
    cube([2*(d[0] + c), 2*(d[1] + c), front_z - d[2] + c]);
  for (s = [-1, 1])
    translate([p[0] + s*(d[3] + 0.5), p[1], disperser_back_z - korry_tab_depth/2])
      cube([1 + 2*c, 2*(d[4] + c), korry_tab_depth + 2*c], center = true);
}

// only the korries close enough to touch a block at (x, y)
module korry_keepouts_near(x, y, r = 25) {
  for (p = korry_efis_pos)
    if (abs(p[0] - x) < r && abs(p[1] - y) < r) korry_keepout(p, korry_efis_dims);
  for (p = korry_button_pos)
    if (abs(p[0] - x) < r && abs(p[1] - y) < r) korry_keepout(p, korry_button_dims);
}

// the main infill's panel_edge() ring (1mm wide, infill_edge_depth deep,
// right behind the disperser), grown by korry_clear, so the main bottom
// blocks can sit flush against the disperser plate
module infill_ring_relief() {
  c = korry_clear;
  z1 = disperser_back_z + 0.01;
  z0 = disperser_back_z - infill_edge_depth - c;
  difference() {
    translate([infill_x0 - c, infill_y0 - c, z0])
      cube([infill_w + 2*c, infill_h + 2*c, z1 - z0]);
    translate([infill_x0 + 1 + c, infill_y0 + 1 + c, z0 - 1])
      cube([infill_w - 2 - 2*c, infill_h - 2 - 2*c, z1 - z0 + 2]);
  }
}

// oval M3 self-tap hole: tap_minor across x, tap_major across y, tap_depth deep
module corner_tap_hole(x, y, offset) {
  translate([x, y, front_z - offset - tap_depth])
    scale([tap_minor/tap_major, 1, 1])
      cylinder(h = tap_depth + 1, d = tap_major, $fn = global_fn);
}

// rotated frame whose xz plane is the tilted base, through the front-bottom
// edge: local +y points into the box, local -z runs toward the back
module base_frame() {
  translate([0, -wall, front_z])
    rotate([base_tilt, 0, 0])
      children();
}

// rotated frame whose xz plane is the tilted top, through the front-top
// edge: local -y points into the box, local -z runs toward the back
module top_frame() {
  translate([0, panel_height + wall, front_z])
    rotate([-top_tilt, 0, 0])
      children();
}

// U-shaped rib straddling a seam, following the tilted top, back and tilted bottom walls
module seam_rib(sx) {
  difference() {
    translate([sx - rib_t, -wall, back_z - wall])
      cube([2*rib_t, outer_h, front_z - rib_front_offset - (back_z - wall)]);
    intersection() {
      translate([sx - rib_t - 1, -big/2, back_z + rib_h])
        cube([2*rib_t + 2, big, big]);
      base_frame()
        translate([-big/2, wall + rib_h, -big/2])
          cube([big, big, big]);
      top_frame()
        translate([-big/2, -big - wall - rib_h, -big/2])
          cube([big, big, big]);
    }
  }
}

// distance along a tilted wall (from the front edge) to the back rib
function back_s(t) = (front_z - back_z - rib_h/2 + (wall + rib_h/2)*sin(t)) / cos(t);
bottom_back_s = back_s(base_tilt);
top_back_s    = back_s(top_tilt);

// inner faces of the tilted floor / top where they meet the back wall
back_inner_floor_y = -wall + (front_z - back_z)*tan(base_tilt) + wall/cos(base_tilt);
back_inner_top_y   = panel_height + wall - (front_z - back_z)*tan(top_tilt) - wall/cos(top_tilt);

module rib_hole() {
  rotate([0, 90, 0])
    cylinder(h = 2*rib_t + 2, d = rib_hole_d, center = true, $fn = global_fn);
}

module seam_rib_holes(sx) {
  // tilted top wall, front to back (last one is the top-back corner)
  for (s = [30, top_back_s/2, top_back_s])
    top_frame() translate([sx, -(wall + rib_h/2), -s]) rib_hole();
  // (back wall middle: an alignment tab instead of a bolt -- see seam_tabs())
  // tilted bottom wall, front to back (last one is the bottom-back corner)
  for (s = [35, bottom_back_s/2, bottom_back_s])
    base_frame() translate([sx, wall + rib_h/2, -s]) rib_hole();
}

module enclosure() {
  difference() {
    union() {
      difference() {
        translate([box_x0 - wall, -wall, back_z - wall])
          cube([box_x1 - box_x0 + 2*wall, outer_h, depth + wall + panel_depth]);

        // full-width/height opening across all three panels, flush with the front face
        translate([box_x0, 0, back_z])
          cube([box_x1 - box_x0, panel_height, depth + panel_depth + 1]);
      }
      for (p = corner_positions)
        corner_block(p[0], p[1], p[2], p[3], p[4]);
      for (p = corner_pads)
        corner_pad(p[0], p[1], p[2], p[3]);
      for (sx = seams)
        seam_rib(sx);

      // tilted bottom wall, replacing the flat one the base cut removes
      intersection() {
        translate([box_x0 - wall, -wall, back_z - wall])
          cube([box_x1 - box_x0 + 2*wall, outer_h, depth + wall + panel_depth]);
        base_frame()
          translate([-big/2, 0, -big/2])
            cube([big, wall, big]);
      }

      // tilted top wall, replacing the flat one the top cut removes
      intersection() {
        translate([box_x0 - wall, -wall, back_z - wall])
          cube([box_x1 - box_x0 + 2*wall, outer_h, depth + wall + panel_depth]);
        top_frame()
          translate([-big/2, -wall, -big/2])
            cube([big, wall, big]);
      }
    }

    // everything below the tilted base
    base_frame()
      translate([-big/2, -big, -big/2])
        cube([big, big, big]);

    // everything above the tilted top
    top_frame()
      translate([-big/2, 0, -big/2])
        cube([big, big, big]);

    // keep the panels' pocket clear of the tilted walls at the front edge
    translate([box_x0, 0, front_z - panel_depth])
      cube([box_x1 - box_x0, panel_height, panel_depth + 1]);

    for (p = corner_positions)
      corner_tap_hole(p[0], p[1], p[2]);
    for (sx = seams)
      seam_rib_holes(sx);

    // korry housings reaching the seam ribs / tilted floor
    korry_keepouts_all();

    usb_cutout();
  }
}

module usb_cutout() {
  translate([usb_x, usb_y, back_z - wall - 1])
    linear_extrude(height = wall + 2)
      offset(r = usb_r) offset(delta = -usb_r)
        square([usb_w, usb_h], center = true);
}

module part_clip(x0, x1) {
  intersection() {
    children();
    translate([x0, -big/2, -big/2])
      cube([x1 - x0, big, big]);
  }
}

// alignment tabs at each seam, to hold the parts in register before the rib
// bolts go in: the main part grows a tab out of each rib face (one each on
// the top, back and bottom ribs), the side part gets a matching pocket.
// Both ends are 45deg so the top/bottom ones print unsupported with the back
// wall on the bed, and double as a lead-in when pushing the parts together.
tab_w      = 4;    // across the rib (along its height off the wall)
tab_len    = 10;   // along the wall, at the rib face
tab_p      = 3;    // protrusion into the neighbour's rib (< rib_t)
tab_taper  = 0.5;  // side lead-in, each side, at the tip
tab_clear  = 0.2;  // pocket clearance, each side

// top/bottom tabs sit midway between the front and middle rib bolts
top_tab_s    = (30 + top_back_s/2) / 2;
bottom_tab_s = (35 + bottom_back_s/2) / 2;

// back tab: replaces the back wall's middle bolt, running tab_len along the
// rib (up the back wall). Its long edges (facing print z) slope at 45deg so
// they print unsupported, which needs it deeper than tab_w: back_tab_h at
// the rib face, narrowing to back_tab_h - 2*tab_p at the tip. Centred in
// the rib + back wall thickness so its pocket stays inside both faces.
back_tab_h = 8;
back_tab_y = (back_inner_floor_y + back_inner_top_y)/2;
back_tab_z = back_z + (rib_h - wall)/2;

// tab pointing +x out of the x=0 plane, centred on the local origin: w along
// y, narrowing by wt each side at the tip; l along z, narrowing by lt each
// side (lt = tab_p gives 45deg faces). c grows it into its pocket.
module tab_shape(c = 0, w = tab_w, wt = tab_taper, l = tab_len, lt = tab_p) {
  hull() {
    translate([-0.5, -(w/2 + c), -(l/2 + c)])
      cube([0.5 + 0.01, w + 2*c, l + 2*c]);
    translate([tab_p + c - 0.01, -(w/2 - wt + c), -(l/2 - lt + c)])
      cube([0.01, w - 2*wt + 2*c, l - 2*lt + 2*c]);
  }
}

// a seam's tabs (top, back, bottom), pointing out of the main part into the side part
module seam_tabs(sx, c = 0) {
  dir = sx < panel_width/2 ? -1 : 1;
  top_frame() translate([sx, -(wall + rib_h/2), -top_tab_s])
    mirror([dir < 0 ? 1 : 0, 0, 0]) tab_shape(c);
  translate([sx, back_tab_y, back_tab_z])
    mirror([dir < 0 ? 1 : 0, 0, 0]) tab_shape(c, w = tab_len, l = back_tab_h);
  base_frame() translate([sx, wall + rib_h/2, -bottom_tab_s])
    mirror([dir < 0 ? 1 : 0, 0, 0]) tab_shape(c);
}

if (part == "left")
  difference() {
    part_clip(box_x0 - wall - 1, 0) enclosure();
    seam_tabs(0, tab_clear);
  }
else if (part == "main")
  union() {
    part_clip(0, panel_width) enclosure();
    for (sx = seams) seam_tabs(sx);
  }
else if (part == "right")
  difference() {
    part_clip(panel_width, box_x1 + wall + 1) enclosure();
    seam_tabs(panel_width, tab_clear);
  }
else
  enclosure();
