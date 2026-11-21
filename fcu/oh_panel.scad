// Overhead panel, layout traced from Ultra-Compact-OVH-3-scaled.jpg
show_infill = false;
infill_type = "all"; // [all, slice]

// Photo panel edges in image pixels (image viewed at 2212px wide)
img_x0 = 105;
img_x1 = 2110;
img_y0 = 305;
img_y1 = 1390;

panel_width = 246; // EMER EXIT name ~5 mm from the right edge, like RWY TURN OFF on the left
// Long divider and top row sit this far below the photo trace; the lower half
// has no section titles above its content
top_drop = 5.5;
panel_height = 110; // ~5.3 mm above the two-line top-row names
panel_depth = 3;
disperser_panel_depth = 2;

// Image pixel -> panel mm, y flipped so panel origin is bottom-left.
// Photo spans the left 220 mm; the ENG section extends past it.
img_scale = 220 / (img_x1 - img_x0);
function ix(px) = (px - img_x0) * img_scale;
function iy(py) = (img_y1 - py) * img_scale;

label_size = 3.2;
title_size = 4.5;

// to cover panel depth
extrude_depth = panel_depth;

global_fn = 32;

module panel(panel_width = panel_width, panel_height = panel_height, x0 =0, y0 =0, z0=0, depth=panel_depth) {
  difference() {
    translate([x0, y0, z0-depth/2]) {
      linear_extrude(height = depth) {
          square([panel_width, panel_height]);
      }
    }

    hole_diameter = 3.2;
    inset = 4;
    // Position four holes at the corners
    for (x = [inset, panel_width - inset]) {
      for (y = [inset, panel_height - inset]) {
        translate([x0+x, y0+y, -depth/2])
          cylinder(d = hole_diameter, h = depth, $fn = global_fn);
      }
    }
  }
}

module panel_edge(panel_width=panel_width, panel_height=panel_height, x0=0, y0=0, z0=0, depth=panel_depth) {
  difference() {
    translate([x0, y0, z0-depth/2]) {
      linear_extrude(height = depth) {
          square([panel_width, panel_height]);
      }
    }
    translate([x0+1, y0+1, z0-depth/2]) {
      linear_extrude(height = depth) {
          square([panel_width-2, panel_height-2]);
      }
    }
  }
}

module korry_housing_tongues(x, y, half_width, scale_factor, cut_through, flange_z_raw, tongue_length,
  top_groove_offset=4, groove_height=2, groove_depth=0.6, tongue_clearance=0.1, chamfer=0.4) {
  overlap = 0.05; // extra overlap into the tab, avoids a coincident face

  groove_z_raw = flange_z_raw - top_groove_offset/scale_factor;
  groove_z = groove_z_raw * scale_factor + (cut_through ? 2 : 0);

  // Clamp/compute in raw units first (matching clip_arm_right()'s own
  // math exactly), then scale once for placement.
  tongue_height_raw = groove_height - 0.4;
  tongue_chamfer_raw = min(chamfer, groove_depth, tongue_height_raw);
  tongue_height = tongue_height_raw * scale_factor;
  tongue_chamfer = tongue_chamfer_raw * scale_factor;
  tongue_reach = (groove_depth - tongue_clearance) * scale_factor;

  top_z = groove_z + tongue_height/2; // sharp edge, same at base and tip
  base_bottom_z = groove_z - tongue_height/2;
  tip_bottom_z = base_bottom_z + tongue_chamfer;

  // Right tongue: base at the tab's inner face (with a small overlap
  // into the tab), tip reaching inward toward the groove's inner wall.
  hull() {
    translate([x+half_width+overlap, y, (top_z+base_bottom_z)/2])
      cube([0.001, tongue_length, top_z-base_bottom_z], center=true);
    translate([x+half_width-tongue_reach, y, (top_z+tip_bottom_z)/2])
      cube([0.001, tongue_length, top_z-tip_bottom_z], center=true);
  }
  // Left tongue: mirror image.
  hull() {
    translate([x-half_width-overlap, y, (top_z+base_bottom_z)/2])
      cube([0.001, tongue_length, top_z-base_bottom_z], center=true);
    translate([x-half_width+tongue_reach, y, (top_z+tip_bottom_z)/2])
      cube([0.001, tongue_length, top_z-tip_bottom_z], center=true);
  }
}

// Lit rectangle around a korry cutout
korry_cutout = 16.2;
korry_outline_gap = 0.5;    // cutout edge to the lit rectangle, at least one 0.4 mm perimeter of panel colour
korry_outline_width = 1;   // matches panel_line's default width, wide enough for 2 perimeters
korry_outline_half = korry_cutout/2 + korry_outline_gap + korry_outline_width; // centre to outer edge
module korry_outline(x, y, cutout=korry_cutout, r=0.8, gap=korry_outline_gap, width=korry_outline_width) {
  translate([x, y, -extrude_depth/2])
    linear_extrude(height = extrude_depth)
      difference() {
        offset(r = r + gap + width) square(cutout - 2*r, center=true);
        offset(r = r + gap) square(cutout - 2*r, center=true);
      }
}

module korry_button(x, y, cut_through=false, infill=false, scale_factor=0.8, outline=true) {
  if (outline && !cut_through) korry_outline(x, y);

  base = "../existing_files/airbus-a320-korry-style-switch-for-3mm-panels-model_files/";
  lower_stl = str(base, "20mm-acrylic-dual-led-korry-ma32-2-lower-housing.stl");
  upper_stl = str(base, "20mm-acrylic-dual-led-korry-ma32-3-upper-housing.stl");

  // Front (visible) face of both parts sits at local z=-3.0 (measured
  // from their bounding boxes).
  growth = cut_through ? 18.52 / 18.32 : 1;

  if (!infill) {
    translate([x, y, cut_through ? 2 : 0]) {
      scale([growth, growth, 1])
        scale([scale_factor, scale_factor, scale_factor])
          hull() {
            import(lower_stl, convexity=10);
            import(upper_stl, convexity=10);
          }
    }

    r = 0.8;
    translate([x, y, -extrude_depth/2]) {
      linear_extrude(height = extrude_depth) {
        offset(r = r)
          offset(delta = -r)
            square([16.2,16.2], center=true);
      }
    }
  }

  if (infill) {
    housing_half_width = 11.95;
    tab_width = 1;
    tab_depth = 5;
    z_offset = -(panel_depth/2+disperser_panel_depth/2) - disperser_panel_depth/2  -tab_depth/2;
    half_width = housing_half_width * scale_factor * growth - 0.3;
    // tabs to match housings
    translate([x+half_width+tab_width/2, y, z_offset]) {
      cube([1,half_width*1.5,tab_depth], center=true);
    }
    translate([x-half_width-tab_width/2, y, z_offset]) {
      cube([1,half_width*1.5,tab_depth], center=true);
    }
    korry_housing_tongues(x, y, half_width, scale_factor, cut_through, -3.0, half_width*1.5);
  }
}

module rotary(x, y, infill=false, cut_through=false, encoder_d=7.5, inset=false) {
  extrude = cut_through ? extrude_depth+disperser_panel_depth : extrude_depth;
  start_z = cut_through ? -disperser_panel_depth : 0;
  if (!infill) {
    translate([x,y,start_z])
      cylinder(extrude, d=encoder_d, center=true);
  }

  if (inset && !infill) {
    translate([x,y,1])
      cylinder(2, d=22, center=true);
  }

  if (!cut_through && encoder_d == 7.5 && !inset) {
    translate([x,y,0])
      difference() {
        cylinder(extrude, d=encoder_d+3, center=true);
        cylinder(extrude, d=encoder_d+0, center=true);
      }
  }
}

module inset_button(x, y, d = 8, cut_through=false) {
  extrude = cut_through ? extrude_depth+disperser_panel_depth : extrude_depth;
  start_z = cut_through ? -disperser_panel_depth : 0;
  translate([x,y,start_z])
    cylinder(extrude, d=d, center=true);
}

module inset_button_ring(x, y, d = 8, infill=false, cut_through=false, nut_d=10, nut_depth=1.5) {
  if (!cut_through) {
    translate([x,y,0])
      difference() {
        cylinder(extrude_depth, d=d+4.5, center=true); // 1mm further out than the button
        cylinder(extrude_depth, d=d+3.0, center=true);
      }
    // Recess on the front face so the mounting nut sits closer to flush;                                    
    // stays clear of the illuminated ring's inner edge (d+3.0)                                              
    
  }

  if (!infill) {
    inset_button(x, y, cut_through=cut_through);
    translate([x, y, extrude_depth/2 - nut_depth/2])                                                         
      cylinder(nut_depth, d=nut_d, center=true);       
  }
}

module illuminated_ring(ring_d, degrees) {
  rotate_extrude(angle = degrees, $fa = 2, $fs = 0.5)
    translate([ring_d/2, 0]) square([1.0, extrude_depth]);
}

module panel_text(x, y, text_string, size=label_size, infill=false) {
  translate([x,y,-extrude_depth/2])
    linear_extrude(height = extrude_depth) {
      offset(delta = 0.15)
        text(text_string, size=size, halign="center", valign="center", font="Futura", spacing=1.1);
    }
}

// push moves just the label further out along its angle; the tick stays put
module ring_text(cx, cy, radius, angle, text_string, label_gap=3, line_width=0.6, line_length=4.3, size=label_size, push=0, infill=false) {
  text_offset = 1.05;
  x = cx + (radius * text_offset + push) * cos(angle);
  y = cy + (radius * text_offset + push) * sin(angle);

  x1 = cx + (radius - line_length) * cos(angle);
  y1 = cy + (radius - line_length) * sin(angle);
  x2 = cx + (radius - label_gap) * cos(angle);
  y2 = cy + (radius - label_gap) * sin(angle);

  translate([0, 0, -extrude_depth/2])
    linear_extrude(height = extrude_depth)
      hull() {
        translate([x1, y1]) circle(d = line_width, $fn = 12);
        translate([x2, y2]) circle(d = line_width, $fn = 12);
      }

  panel_text(x, y, text_string, size=size, infill=infill);
}

// Engraved line between two panel points (mm)
module panel_line(p1, p2, width=1) {
  translate([0, 0, -extrude_depth/2])
    linear_extrude(height = extrude_depth)
      hull() {
        translate(p1) square(width, center=true);
        translate(p2) square(width, center=true);
      }
}

// 3-position selector over 90 degrees centred on north, name above the middle label.
// labels = [left, north, right]
module selector_90(cx, cy, name, labels, infill=false, cut_through=false) {
  name_gap = 22; // centre to name text
  ring_d = 22;
  first_angle = 45;
  last_angle = 135;
  if (!cut_through) {
    translate([cx, cy, -extrude_depth/2])
      rotate([0, 0, first_angle])
        illuminated_ring(ring_d, last_angle - first_angle);
  }
  rotary(cx, cy, infill=infill, cut_through=cut_through, encoder_d=9.5);

  for (l = [
    [last_angle, labels[0]],
    [(first_angle + last_angle) / 2, labels[1]],
    [first_angle, labels[2]],
  ])
    ring_text(cx, cy, 16, l[0], l[1], infill=infill);

  panel_text(cx, cy + name_gap, name, infill=infill);
}

// OLED module, same board and window as front_panel.scad
oled_board_w = 33;       // board width (mm)
oled_board_h = 28;       // board height, bottom (notch) to top (header) (mm)
oled_window_w = 25;      // front cutout width (mm)
oled_window_h = 14;      // front cutout height (mm)
oled_window_top_gap = 4; // board top edge -> top of window (mm), clears header strip

// OLED board centred at (bx, by). Front panel gets the display window; the
// diffuser gets the whole board footprint so the board sits flat on the
// panel's back face. Preview also shows the board outline behind.
module oled_window(bx, by, infill=false, cut_through=false) {
  wy = by + oled_board_h/2 - oled_window_top_gap - oled_window_h/2;
  if (!infill && !cut_through)
    translate([bx, wy, 0])
      cube([oled_window_w, oled_window_h, extrude_depth + 0.2], center=true);
  if (cut_through)
    translate([bx, by, -(panel_depth/2 + disperser_panel_depth/2)])
      cube([oled_board_w + 1, oled_board_h + 1, disperser_panel_depth + 0.4], center=true);
  if ($preview && !infill && !cut_through)
    %translate([bx, by, -extrude_depth/2 - 0.8])
      cube([oled_board_w, oled_board_h, 1.6], center=true);
}

// Pegs on the panel's back face for the board's corner holes, same spacing
// and size as front_panel.scad's rear_mount
module oled_mount(bx, by) {
  mount_depth = 4;
  z_offset = -panel_depth/2 - mount_depth/2;
  for (dx = [5, 28], dy = [3, 27])
    translate([bx - oled_board_w/2 + dx, by - oled_board_h/2 + dy, z_offset])
      cylinder(5, d=1.5, center=true, $fn=global_fn);
}

// ENG section on the right of the lower half (divider set with the lower-half grid)
eng_master_dx = 17.5;     // ENG 1/2 toggles either side of MODE, names clear of its ring ticks

// Top row, grouped by system: GPWS | fuel | air | elec | hyd | wiper.
// Each entry: [kind, labels, spacing from the previous item,
//              starts a new group (gets a divider before it)]
// spacing: "first" for the first item, "pitch" korry to korry within a group,
// "side" X BLEED to PACK 1/2, "group" across a group divider, "oled" korry to OLED
korry_pitch = 24.8;  // korry to korry within a group
side_clear = 3.65;   // X BLEED's AUTO label to the PACK 1/2 outline
top_side_dx = 9;     // toggle centre to its vertical middle-position label
korry_to_oled = 28;   // board clears the korry housing and BAT label
// Centre-to-centre distance that leaves `clear` between two items' extents
function top_gap(prev_kind, kind, clear) = top_extent(prev_kind)[1] + clear + top_extent(kind)[0];
top_row = [
  ["korry",  ["LDG", "FLAP 3"],  "first", false],
  ["korry",  ["FUEL", "PUMPS"],  "group", true],
  ["xbleed", [],                 "group", true],
  ["korry",  ["PACK 1/2"],       "side",  false],
  ["korry",  ["APU BLEED"],      "pitch", false],
  ["korry",  ["EXT PWR"],        "group", true],
  ["korry",  ["BAT 1/2"],        "pitch", false],
  // ["oled",   [],                 "oled",  false],
  ["korry",  ["Y ELEC", "PUMP"], "group", true],
  ["wiper",  [],                 "group", true],
];
function top_dist(i, gc) = let(s = top_row[i][2], pk = top_row[i - 1][0], k = top_row[i][0])
  s == "pitch" ? korry_pitch :
  s == "side"  ? top_gap(pk, k, side_clear) :
  s == "oled"  ? korry_to_oled :
  top_gap(pk, k, gc);
function top_offset_gc(i, gc) = i == 0 ? 0 : top_offset_gc(i - 1, gc) + top_dist(i, gc);
// Row spans the long divider: LDG FLAP 3's outline starts at its left end and
// WIPER's SLOW label ends at its right end; the slack is shared evenly across
// the group gaps, each divider midway in its gap
top_last = len(top_row) - 1;
top_left = ix(162) - 0.5;
top_right = panel_width - ix(162) + 0.5;
top_groups = len([for (r = top_row) if (r[2] == "group") 1]);
top_span_no_gaps = top_extent(top_row[0][0])[0] + top_offset_gc(top_last, 0) + top_extent(top_row[top_last][0])[1];
group_clear = (top_right - top_left - top_span_no_gaps) / top_groups;
function top_offset(i) = top_offset_gc(i, group_clear);
top_x0 = top_left + top_extent(top_row[0][0])[0];
function top_x(i) = top_x0 + top_offset(i);

// How far each kind reaches left / right of its centre, so group dividers
// sit midway in the clear gap rather than midway between centres
function top_extent(kind) =
  kind == "xbleed" ? [9.3, 11.1] :                   // X BLEED name / vertical AUTO
  kind == "oled"   ? [oled_board_w/2 + 0.5, oled_board_w/2 + 0.5] :
  kind == "wiper"  ? [7.7, 11.8] :                   // WIPER name / vertical SLOW
  [korry_outline_half, korry_outline_half];          // korry outline
function top_divider_x(i) =
  (top_x(i - 1) + top_extent(top_row[i - 1][0])[1] + top_x(i) - top_extent(top_row[i][0])[0]) / 2;
top_korry_y = 90.3 - top_drop;
top_label_y = top_korry_y + 15.5; // single-line name; two-line names sit 2.1 above / below
// Board centre: display window centre 17.7 mm above the long divider, which
// keeps the board's bottom edge clear of it
top_oled_window_y = 94.3 - top_drop;
top_oled_y = top_oled_window_y - (oled_board_h/2 - oled_window_top_gap - oled_window_h/2);
// top_oled_x = top_x([for (i = [0:len(top_row)-1]) if (top_row[i][0] == "oled") i][0]);

// 3-way toggle in the top row: name on the korry name line, up / down labels
// above / below the hole, middle position stacked vertically to the right
module top_toggle(x, name, up, mid, down, infill, cut_through) {
  y = top_label_y - name_dy;
  light_switch(x, y, name, up, down, infill, cut_through);
  vertical_text(x + top_side_dx, y, mid, infill=infill);
}

module ohp(infill=false, cut_through=false) {
  for (i = [0:len(top_row)-1]) {
    x = top_x(i);
    kind = top_row[i][0];
    names = top_row[i][1];
    if (kind == "korry") {
      korry_button(x, top_korry_y, infill=infill, cut_through=cut_through);
      if (len(names) == 2) {
        panel_text(x, top_label_y + 2.1, names[0], infill=infill);
        panel_text(x, top_label_y - 2.1, names[1], infill=infill);
      } else {
        panel_text(x, top_label_y, names[0], infill=infill);
      }
    } else if (kind == "xbleed") {
      top_toggle(x, "X BLEED", "ON", "AUTO", "OFF", infill, cut_through);
    } else if (kind == "oled") {
      oled_window(x, top_oled_y, infill=infill, cut_through=cut_through);
    } else if (kind == "wiper") {
      top_toggle(x, "WIPER", "FAST", "SLOW", "OFF", infill, cut_through);
    }
    // Group divider, same gaps to the long divider and panel edge as the
    // lower-half dividers
    if (top_row[i][3])
      panel_line([top_divider_x(i), long_div_y + (long_div_y - div_top)],
                 [top_divider_x(i), panel_height - div_bottom]);
  }

  // Lower half is laid out in mm on a grid; everything above it sits
  // top_drop lower than the photo trace
  div_top = 73.3 - top_drop;    // ~1.2 mm above the APU title
  div_bottom = 5.5;
  long_div_y = iy(692) - top_drop;

  // Long divider, same margin from both panel edges
  panel_line([ix(162), long_div_y], [panel_width - ix(162), long_div_y]);
  panel_line([apu_div_l, div_top], [apu_div_l, div_bottom]);
  panel_line([apu_div_r, div_top], [apu_div_r, div_bottom]);
  panel_line([anti_ice_div, div_top], [anti_ice_div, div_bottom]);

  // ENG: title level with the APU title, MODE selector (CRK / NORM / IGN)
  // between the ENG 1/2 master toggles, one FIRE/FAULT korry shared by both
  // engines centred below; heights set with the lower-half grid
  panel_text(eng_x, 64, "ENG", size=title_size, infill=infill);
  for (i = [0:1])
    light_switch(eng_x + (i == 0 ? -1 : 1) * eng_master_dx, eng_row_y, str("ENG ", i + 1), "ON", "OFF", infill, cut_through);
  selector_90(eng_x, eng_mode_y, "MODE", ["CRK", "NORM", "IGN"], infill=infill, cut_through=cut_through);
  korry_button(eng_x, eng_korry_y, infill=infill, cut_through=cut_through);

  // EXT LT: 4 evenly spaced columns x 2 rows
  c1 = lt_cols[0];
  c2 = lt_cols[1];
  c3 = lt_cols[2];
  c4 = lt_cols[3];
  r1 = lt_rows[0];
  r2 = lt_rows[1];
  side_dx = 9;

  light_switch(c1, r1, "STROBE", "ON", "OFF", infill, cut_through);
  vertical_text(c1 + side_dx, r1, "AUTO", infill=infill);

  light_switch(c2, r1, "BEACON", "ON", "OFF", infill, cut_through);
  light_switch(c3, r1, "WING", "ON", "OFF", infill, cut_through);
  light_switch(c4, r1, ["NAV &", "LOGO"], "2", "OFF", infill, cut_through);
  panel_text(c4 + side_dx, r1, "1", infill=infill);

  light_switch(c1, r2, ["RWY", "TURN OFF"], "ON", "OFF", infill, cut_through);

  // LAND L/R share ON/OFF/RETRACT between them under a bracket. Bracket
  // lines match the divider width; the gap clears "LAND" (13 mm wide); the
  // ticks sit out at the left/right edges of each toggle's ring rather
  // than dropping down its centre, same tick length as before.
  land_mid = (c2 + c3) / 2;
  land_gap = 8.5; // half gap in the bracket for the LAND text
  toggle_ring_outer_r = (8 + 4.5) / 2; // matches inset_button_ring's default outer dia
  land_left = c2 - toggle_ring_outer_r;
  land_right = c3 + toggle_ring_outer_r;
  tick = 1.8;
  land_line_width = 1;
  land_y = r2 + name_dy;
  toggle_switch(c2, r2, infill, cut_through);
  toggle_switch(c3, r2, infill, cut_through);
  panel_text(land_mid, land_y, "LAND", infill=infill);
  panel_line([land_left, land_y], [land_mid - land_gap, land_y], width=land_line_width);
  panel_line([land_mid + land_gap, land_y], [land_right, land_y], width=land_line_width);
  panel_line([land_left, land_y], [land_left, land_y - tick], width=land_line_width);
  panel_line([land_right, land_y], [land_right, land_y - tick], width=land_line_width);
  panel_text(c2, r2 + on_dy, "L", infill=infill);
  panel_text(c3, r2 + on_dy, "R", infill=infill);
  panel_text(land_mid, r2 + on_dy, "ON", infill=infill);
  panel_text(land_mid, r2, "OFF", infill=infill);
  panel_text(land_mid, r2 + off_dy, "RETRACT", infill=infill);

  light_switch(c4, r2, "NOSE", "T.O", "OFF", infill, cut_through);
  vertical_text(c4 + side_dx, r2, "TAXI", infill=infill);

  // EXT LT small title: row 1's names already reach almost to div_top, so the
  // title sits just under the long divider line instead, clear of both it
  // and the BEACON / WING names below
  ext_lt_title_y = long_div_y - 3.1;
  panel_text((c1 + c4) / 2, ext_lt_title_y, "EXT LT", infill=infill);

  // APU
  apu_x = (apu_div_l + apu_div_r) / 2;
  panel_text(apu_x, 64, "APU", size=title_size, infill=infill); // ~2 mm above MASTER
  panel_text(apu_x, 57.5, "MASTER", infill=infill);
  korry_button(apu_x, 43, infill=infill, cut_through=cut_through);
  panel_text(apu_x, 28, "START", infill=infill);
  korry_button(apu_x, 15, infill=infill, cut_through=cut_through);

  // ANTI ICE: small title over the two korries, heights set with the lower-half grid
  ai1 = anti_ice_cols[0];
  ai2 = anti_ice_cols[1];
  panel_text((ai1 + ai2) / 2, ai_title_y, "ANTI ICE", infill=infill);
  panel_text(ai1, ai_label_y, "WING", infill=infill);
  korry_button(ai1, ai_korry_y, infill=infill, cut_through=cut_through);
  panel_text(ai2, ai_label_y, "ENG 1/2", infill=infill);
  korry_button(ai2, ai_korry_y, infill=infill, cut_through=cut_through);

  // Line between the ANTI ICE korries and the SEAT BELTS / EMER EXIT toggles,
  // midway between the korry outlines and the toggle names. It stops short of
  // the vertical divider by the same gap the dividers leave below the long
  // divider, and runs to the long divider's right end.
  ai_line_y = (ai_korry_y - korry_outline_half + r2 + name_dy + 1.8) / 2;
  panel_line([anti_ice_div + (long_div_y - div_top), ai_line_y], [panel_width - ix(162), ai_line_y]);

  light_switch(ai1, r2, "SEAT BELTS", "ON", "OFF", infill, cut_through);

  light_switch(ai2, r2, "EMER EXIT", "ON", "OFF", infill, cut_through);
  vertical_text(ai2 + side_dx, r2, "ARM", infill=infill);
}

// Lower-half grid (mm)
// EXT LT columns: pitch set by the STROBE / BEACON names and the OFF label
// between LAND L and R
lt_x0 = 17;
lt_pitch = 23;
lt_cols = [for (i = [0:3]) lt_x0 + i*lt_pitch];
lt_rows = [49, 16];
// Sections to the right follow the EXT LT columns
apu_div_l = lt_cols[3] + 13;  // clears the NOSE TAXI label
apu_div_r = apu_div_l + 30.5; // APU korry outlines ~5 mm from each divider
// ENG next, its ENG 1 / ENG 2 names ~3 mm clear of the dividers either side
eng_half = eng_master_dx + 7.5 + 3;
eng_x = apu_div_r + eng_half;
anti_ice_div = eng_x + eng_half;
// ANTI ICE last, spread so SEAT BELTS and EMER EXIT names fit on one line;
// SEAT BELTS name ~2 mm clear of the divider
anti_ice_cols = [anti_ice_div + 15.5, anti_ice_div + 43.5];
// ANTI ICE heights: small title ~1.4 mm above the WING / ENG 1/2 names, which
// sit 14 mm above their korries; the korries leave ~1 mm either side of the
// line above the SEAT BELTS / EMER EXIT names
ai_title_y = 65.5;
ai_label_y = ai_title_y - 5;
ai_korry_y = ai_label_y - 14;

// Toggle label offsets from the hole centre
name_dy = 14.5;
on_dy = 9.5;
off_dy = -9.5;
name_line_gap = 4.2; // between lines of a two-line toggle name

// ENG heights: MODE name level with APU MASTER; ENG 1/2 names sit just under
// the CRK / IGN labels; FIRE korry outline ~1 mm under the 22 mm knob
eng_mode_y = 57.5 - 22; // selector_90's centre to name gap
eng_row_y = eng_mode_y - 8;
eng_korry_y = eng_mode_y - 11 - 1 - korry_outline_half;

module toggle_switch(x, y, infill, cut_through) {
  inset_button_ring(x, y, infill=infill, cut_through=cut_through);
}

// Toggle with name, ON and OFF labels centred on the hole. A name given as a
// list goes on two lines, the last one on the usual name line.
module light_switch(x, y, name, on, off, infill, cut_through) {
  toggle_switch(x, y, infill, cut_through);
  lines = is_list(name) ? name : (name == "" ? [] : [name]);
  for (i = [0:1:len(lines)-1])
    panel_text(x, y + name_dy + (len(lines) - 1 - i) * name_line_gap, lines[i], infill=infill);
  if (on != "") panel_text(x, y + on_dy, on, infill=infill);
  if (off != "") panel_text(x, y + off_dy, off, infill=infill);
}

// Letters stacked top to bottom, centred vertically on y
module vertical_text(x, y, s, pitch=4.2, infill=false) {
  n = len(s);
  for (i = [0:n-1])
    panel_text(x, y + ((n-1)/2 - i) * pitch, s[i], infill=infill);
}

module oh_panel(infill = false) {
  if (infill) {
    // Clip to the panel so nothing past its edges prints as loose bits
    intersection() {
      ohp(infill);
      translate([0, 0, -50]) cube([panel_width, panel_height, 100]);
    }
    // Diffuser plate, full panel size
    difference() {
      translate([0, 0, -panel_depth/2 - disperser_panel_depth])
        cube([panel_width, panel_height, disperser_panel_depth]);
      ohp(cut_through=true);
      // Front panel's corner holes carried through, so the screws reach the
      // enclosure's corner blocks
      for (x = [4, panel_width - 4], y = [4, panel_height - 4])
        translate([x, y, -25]) cylinder(d = 3.2, h = 50, $fn = global_fn);
    }
  } else {
    union() {
      difference() {
        panel();
        ohp();
      }
      // oled_mount(top_oled_x, top_oled_y);
    }
  }
}

module oh_panel_infill_front_slice(slice_depth=0.4) {
  front_z = disperser_panel_depth - 0.5;
  intersection() {
    oh_panel(infill=true);
    translate([-1000, -1000, front_z - slice_depth])
      cube([2000, 2000, slice_depth]);
  }
}

module oh_panel_infill_back(slice_depth=0.4) {
  front_z = disperser_panel_depth - 0.5;
  intersection() {
    oh_panel(infill=true);
    translate([-1000, -1000, -1000])
      cube([2000, 2000, 1000 + front_z - slice_depth]);
  }
}

if (show_infill) {
  if (infill_type == "slice") {
    oh_panel_infill_front_slice();
  } else {
    oh_panel_infill_back();
  }
} else {
  oh_panel();
}
