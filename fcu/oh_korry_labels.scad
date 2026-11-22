// Overhead panel korry (ma32 button) legends, housings and clips
part = "legends"; // [legends, button_legend, button_light_guide, button_housing, button_housing_clip]

show_infill = false; // set true to render the accent-color text inserts instead

// Single-legend overrides for batch rendering
label_top_text = "FAULT";
label_top_dots = false;
label_bottom_text = "ON";
label_bottom_box = true;

part_spacing = 25;

// Unique legends on oh_panel.scad: [top_text, top_dots, bottom_text, bottom_box].
// Text follows the xplane-config dref deck; render.mjs renders one per korry.
//   ON        : LDG FLAP 3, APU BLEED
//   FAULT/OFF : FUEL PUMPS, PACK 1/2, BAT 1/2
//   FAULT/ON  : Y ELEC PUMP, APU MASTER SW, ANTI ICE WING, ANTI ICE ENG 1/2
//   AVAIL/ON  : EXT PWR, APU START
//   FIRE/FAULT: ENG 1/2 (no box)
legends = [
  ["",      false, "ON",    true],
  ["FAULT", false, "OFF",   true],
  ["FAULT", false, "ON",    true],
  ["AVAIL", false, "ON",    true],
  ["FIRE",  false, "FAULT", false],
];

module panel_text(x, y, text_string, depth, size=2.5, infill=false) {
  translate([x, y, -depth/2])
    linear_extrude(height = depth) {
      offset(delta = 0.25)
        text(text_string, size=size, halign="center", valign="center", font="Futura", spacing=1.1);
    }
}

module rect_outline(x, y, size, depth, line_width=0.6) {
  translate([x, y, -depth/2])
    linear_extrude(height = depth)
      difference() {
        square(size, center=true);
        square([size.x - 2*line_width, size.y - 2*line_width], center=true);
      }
}

// Two indicator dots, as on the LDG FLAP 3 legend
module dots(x, y, depth, spacing=6, d=1.8) {
  translate([x, y, -depth/2])
    linear_extrude(height = depth)
      for (i = [-1, 1])
        translate([i * spacing/2, 0]) circle(d = d, $fn = 24);
}

// button-legend.dxf is a wireframe OpenSCAD can't import, so the tile
// is a plain square sized to its bounding box.
module korry_button_legend(x, y, top_text="", top_dots=false, bottom_text="", bottom_box=false, front_z=0, thickness=3, scale_factor=0.8, text_size=3.0, infill=false) {
  base = "../existing_files/airbus-a320-korry-style-switch-for-3mm-panels-model_files/";
  light_guide_stl = str(base, "20mm-acrylic-dual-led-korry-ma32-1-button-light-guide.stl");
  tile_size = [16, 16];
  bottom_box_size = [15, 7];
  front_face_z = thickness * scale_factor;
  top_line_scale = 1.1;

  module features() {
    if (top_text != "") panel_text(0, 4, top_text, thickness, size=text_size * top_line_scale);
    if (top_dots) dots(0, 4, thickness);
    if (bottom_text != "") panel_text(0, -4, bottom_text, thickness, size=text_size);
    if (bottom_box) rect_outline(0, -4, bottom_box_size, thickness);
  }

  translate([x, y, front_z - front_face_z])
    scale([scale_factor, scale_factor, scale_factor]) {
      // Preview-only: tile sits in a recess on the light guide's front face
      if ($preview) translate([0, 0, thickness]) import(light_guide_stl, convexity=10);

      if (infill) {
        translate([0, 0, thickness/2]) features();
      } else {
        difference() {
          linear_extrude(height = thickness) square(tile_size, center=true);
          translate([0, 0, thickness/2]) features();
        }
      }
    }
}

module korry_button_light_guide(x, y, front_z=0, scale_factor=0.8) {
  base = "../existing_files/airbus-a320-korry-style-switch-for-3mm-panels-model_files/";
  light_guide_stl = str(base, "20mm-acrylic-dual-led-korry-ma32-1-button-light-guide.stl");

  z_cut = -5;
  extend_by = 2;

  // Top face already sits at local z=0
  difference() {
    translate([x, y, front_z])
      scale([scale_factor, scale_factor, scale_factor])
        extend_at(z_cut, extend_by)
          import(light_guide_stl, convexity=10);
    translate([x-1.5, y-1.0, front_z-18.5])
      cube([3,2,3.7]);
  }
}

// Inserts `extra` mm of length at z_cut: everything above stays put,
// everything below slides down rigidly, and the gap is filled by
// extruding the wall cross-section just above the cut. Only valid
// where the wall is a plain, non-tapered profile.
module extend_at(z_cut, extra) {
  if (extra <= 0) {
    children();
  } else {
    epsilon = 0.05;
    big = 1000;
    union() {
      intersection() {
        children();
        translate([-big/2, -big/2, z_cut])
          cube([big, big, big]);
      }
      translate([0, 0, -extra])
        intersection() {
          children();
          translate([-big/2, -big/2, -big])
            cube([big, big, big + z_cut]);
        }
      translate([0, 0, z_cut - extra])
        linear_extrude(height = extra)
          projection(cut = true)
            translate([0, 0, -(z_cut + epsilon)])
              children();
    }
  }
}

// Shallow groove on the outside of the left/right walls for the clip
// tongues. Underside chamfered only, since the housing prints upside
// down; the outer sheet overshoots by epsilon to avoid a coincident face.
module housing_side_groove_cut(groove_z, half_width=11.45, groove_height=2, groove_depth=0.6, chamfer=0.4) {
  epsilon = 0.1;
  chamfer_c = min(chamfer, groove_depth, groove_height);
  top_z = groove_z + groove_height/2;
  outer_bottom_z = groove_z - groove_height/2;
  inner_bottom_z = outer_bottom_z + chamfer_c;

  for (side = [-1, 1]) {
    outer_x = side * (half_width + epsilon);
    inner_x = side * (half_width - groove_depth);
    hull() {
      translate([outer_x, 0, (top_z + outer_bottom_z)/2])
        cube([0.001, 1000, top_z - outer_bottom_z], center=true);
      translate([inner_x, 0, (top_z + inner_bottom_z)/2])
        cube([0.001, 1000, top_z - inner_bottom_z], center=true);
    }
  }
}

// One clip side (+x): strap against the housing wall plus a tongue
// reaching into the groove, overlapping the strap to stay manifold.
module clip_arm_right(half_width, arm_width, groove_z, groove_height, groove_depth, tongue_clearance, arm_top, arm_bottom, clip_depth, chamfer=0.4) {
  overlap = 0.05;
  arm_center_z = (arm_top + arm_bottom) / 2;
  arm_height = arm_top - arm_bottom;

  translate([half_width + arm_width/2, 0, arm_center_z])
    cube([arm_width, clip_depth, arm_height], center=true);

  tongue_height = groove_height - 0.4;
  tongue_chamfer = min(chamfer, groove_depth, tongue_height);
  tongue_reach = groove_depth - tongue_clearance;
  top_z = groove_z + tongue_height/2;
  base_bottom_z = groove_z - tongue_height/2;
  tip_bottom_z = base_bottom_z + tongue_chamfer;
  hull() {
    translate([half_width + overlap, 0, (top_z + base_bottom_z)/2])
      cube([0.001, clip_depth, top_z - base_bottom_z], center=true);
    translate([half_width - tongue_reach, 0, (top_z + tip_bottom_z)/2])
      cube([0.001, clip_depth, top_z - tip_bottom_z], center=true);
  }
}

// Slide-on clip gripping the housing grooves, with a floor closing the
// base. groove_offset is real mm from the housing bottom, converted to
// raw units since the whole clip is scaled at the end.
module korry_housing_clip(x=0, y=0, scale_factor=0.8, groove_offset=2.5, half_width=11.45, groove_height=2, groove_depth=0.6, tongue_clearance=0.1, arm_width=1.5, arm_top_margin=1.5, clip_depth=10, floor_thickness=1.5, chamfer=0.4) {
  raw_groove_offset = groove_offset / scale_factor;
  arm_top = raw_groove_offset + groove_height/2 + arm_top_margin;
  arm_bottom = -floor_thickness;

  translate([x, y, 0])
    scale([scale_factor, scale_factor, scale_factor])
      union() {
        clip_arm_right(half_width, arm_width, raw_groove_offset, groove_height, groove_depth, tongue_clearance, arm_top, arm_bottom, clip_depth, chamfer);
        mirror([1, 0, 0])
          clip_arm_right(half_width, arm_width, raw_groove_offset, groove_height, groove_depth, tongue_clearance, arm_top, arm_bottom, clip_depth, chamfer);
        translate([0, 0, -floor_thickness/2])
          cube([2*(half_width + arm_width), clip_depth, floor_thickness], center=true);
        translate([0, -clip_depth/2, (arm_top-arm_bottom)/2-floor_thickness])
          cube([2*(half_width + arm_width), floor_thickness, arm_top-arm_bottom], center=true);
      }
}

module korry_button_housing_clip(x=0, y=0, scale_factor=0.8, groove_offset=4, half_width=11.45, groove_height=2, groove_depth=0.6, tongue_clearance=0.1, arm_width=1.5, arm_top_margin=1.5, clip_depth=20, floor_thickness=1.5, chamfer=0.4) {
  korry_housing_clip(x, y, scale_factor, groove_offset, half_width, groove_height, groove_depth, tongue_clearance, arm_width, arm_top_margin, clip_depth, floor_thickness, chamfer);
}

// Internal dimensions 15.12 x 15.12
module korry_button_housing(x, y, front_z=0, scale_factor=0.8, extend_by=2, extend_offset=2, groove_offset=2.5, top_groove_offset=5) {
  base = "../existing_files/airbus-a320-korry-style-switch-for-3mm-panels-model_files/";
  lower_stl = str(base, "20mm-acrylic-dual-led-korry-ma32-2-lower-housing.stl");
  upper_stl = str(base, "20mm-acrylic-dual-led-korry-ma32-3-upper-housing.stl");

  front_face_z = -3.0; // measured front face of both STLs
  housing_z_min = -32.6; // measured bottom of both STLs
  z_cut = housing_z_min + extend_offset;

  // Offsets are real mm, converted to raw units before the scale below
  groove_z = housing_z_min + groove_offset/scale_factor;
  top_groove_z = front_face_z - top_groove_offset/scale_factor;

  module housing_half(stl_path) {
    difference() {
      import(stl_path, convexity=10);
      if (groove_offset > 0) housing_side_groove_cut(groove_z);
      if (top_groove_offset > 0) housing_side_groove_cut(top_groove_z);
    }
  }

  translate([x, y, front_z - front_face_z * scale_factor])
    scale([scale_factor, scale_factor, scale_factor])
      union() {
        extend_at(z_cut, extend_by) housing_half(lower_stl);
        extend_at(z_cut, extend_by) housing_half(upper_stl);
      }
}


if (part == "legends") {
  for (i = [0:len(legends)-1])
    korry_button_legend(i*part_spacing, 0, top_text=legends[i][0], top_dots=legends[i][1], bottom_text=legends[i][2], bottom_box=legends[i][3], infill=show_infill);
} else if (part == "button_legend") {
  korry_button_legend(0, 0, top_text=label_top_text, top_dots=label_top_dots, bottom_text=label_bottom_text, bottom_box=label_bottom_box, infill=show_infill);
} else if (part == "button_light_guide") {
  korry_button_light_guide(0, 0);
} else if (part == "button_housing") {
  korry_button_housing(0, 0);
} else if (part == "button_housing_clip") {
  korry_button_housing_clip();
}
