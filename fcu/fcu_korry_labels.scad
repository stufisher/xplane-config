part = "all"; // [efis_indicator_legend, button_legend, efis_light_guide, button_light_guide, efis_housing, button_housing, efis_housing_clip, button_housing_clip, all]

show_infill = false; // set true to render the accent-color text inserts instead

// Batch-rendering overrides (see scripts/render_korry_labels.mjs) --
// efis_indicator_legend only uses label_top_shape/label_bottom_text;
// button_legend only uses label_top_text/label_bottom_text/
// label_bottom_box. Each -D'd independently since the two legend
// types take genuinely different parameters (top_shape is an enum on
// the efis one, free text on the button one; only the button one has
// a box option).
label_top_shape = "rect"; // efis: "rect", "lines", or "none"
label_top_text = "FAULT"; // button
label_bottom_text = "APU"; // both
label_bottom_box = true; // button

// Widest footprint among the parts (ma32 housing/light guide, ~20mm)
// plus some margin, so "all" can lay them out in a row without
// overlapping.
part_spacing = 25;


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

module filled_rect(x, y, size, depth) {
  translate([x, y, -depth/2])
    linear_extrude(height = depth)
      square(size, center=true);
}

module bars(x, y, width, depth, count=3, line_width=1, gap=1.5) {
  translate([x, y, -depth/2])
    linear_extrude(height = depth)
      for (i = [0:count-1])
        translate([0, (i - (count-1)/2) * gap])
          square([width, line_width], center=true);
}

module korry_efis_indicator_legend(x, y, top_shape="rect", bottom_text="", front_z=0, scale_factor=0.8, text_size=3, infill=false) {
  base = "../existing_files/airbus-a320-efis-korry-style-switch-model_files/";
  indicator_stl = str(base, "efis-14mm-x-12mm-korry-ma08-button-top-indicator.stl");
  legend_stl = str(base, "efis-14mm-x-12mm-korry-ma08-button-bottom-legend.stl");
  light_guide_stl = str(base, "efis-14mm-x-12mm-korry-ma08-button-light-guide.stl");

  // Both STLs share one coordinate frame: indicator occupies y>0 (top
  // half), legend occupies y<0 (bottom half). Their shared visible/
  // outer face sits at local z=6.0 (measured from bounding boxes; base
  // z=0 sits on the light guide's top face). After scaling, shift so
  // that face sits flush with the panel's front face, given by
  // front_z.
  front_face_z = 6.0 * scale_factor;
  depth = 6; // local z span of both STLs (z=[0,6])

  // Real indicators are plain (a colored patch when lit), not text --
  // "rect" is a small solid indicator patch, "lines" is a 3-bar mark,
  // "none" leaves the indicator half untouched.
  indicator_size = [6, 3];

  module top_features() {
    if (top_shape == "rect") filled_rect(0, 3, indicator_size, depth);
    else if (top_shape == "lines") bars(0, 3, indicator_size.x+2, depth);
  }

  translate([x, y, front_z - front_face_z])
    scale([scale_factor, scale_factor, scale_factor]) {
      // Editor-preview-only reference: the light guide this legend
      // sits on top of, at its own local coordinate frame (its top
      // face is already at z=0, same as the legend's base, so no
      // extra offset is needed). Never appears in an actual F6
      // render/export, only the live F5 preview -- same $preview
      // convention as front_windows() in front_panel.scad.
      if ($preview) import(light_guide_stl, convexity=10);

      if (infill) {
        // Raised shape/text only, at the same position/depth as the
        // slots cut below -- print in a different filament and glue
        // in to fill them with a contrasting color.
        translate([0, 0, depth/2]) {
          top_features();
          if (bottom_text != "") {
            translate([0, 0.2, 0])
              panel_text(0, -3, bottom_text, depth, size=text_size);
          }
        }
      } else {
        difference() {
          // The source STLs each stop 0.1mm short of y=0 (indicator
          // y>=0.1, legend y<=-0.1) -- intentional in the real part,
          // an allowance for the black paint seam glued between the
          // two halves to block light bleed. hull() (rather than
          // union()) bridges that 0.2mm gap so the two stay a single
          // solid here, without moving either STL from its real
          // position.
          hull() {
            import(indicator_stl, convexity=10);
            import(legend_stl, convexity=10);
          }
          translate([0, 0, depth/2]) {
            top_features();
            if (bottom_text != "") {
              translate([0, 0.2, 0])
                panel_text(0, -3, bottom_text, depth, size=text_size);
            }
          }
        }
      }
    }
}

// The button-legend.dxf file holds only a wireframe outline of its
// original 3mm-thick CAD box (two overlapping rectangles, one per Z
// face, joined by zero-length vertical edges once projected) rather
// than a closed 2D profile, so OpenSCAD's DXF import can't parse it
// (confirmed: import() on the file errors "not a 2D object", empty
// result). Reproduced here as a plain square instead, sized to the
// DXF's measured bounding box.

module korry_button_legend(x, y, top_text="", bottom_text="", bottom_box=false, front_z=0, thickness=3, scale_factor=0.8, text_size=3.0, infill=false) {
  base = "../existing_files/airbus-a320-korry-style-switch-for-3mm-panels-model_files/";
  light_guide_stl = str(base, "20mm-acrylic-dual-led-korry-ma32-1-button-light-guide.stl");
  tile_size = [16, 16]; // measured extent of the button-legend.dxf full tile
  bottom_box_size = [15, 7]; // close to the tile's edges within the bottom half
  front_face_z = thickness * scale_factor;

  module bottom_features() {
    if (bottom_text != "") panel_text(0, -4, bottom_text, thickness, size=text_size);
    if (bottom_box) rect_outline(0, -4, bottom_box_size, thickness);
  }

  translate([x, y, front_z - front_face_z])
    scale([scale_factor, scale_factor, scale_factor]) {
      // Editor-preview-only reference: the legend tile sits in a
      // recess on the light guide's front face (glued in per the
      // model notes), not flush on top of it, so shift the light
      // guide up by the tile's thickness to show it fitting inside.
      // Never appears in an actual F6 render/export, only the live F5
      // preview.
      if ($preview) translate([0, 0, thickness]) import(light_guide_stl, convexity=10);

      top_line_scale = 1.1;
      if (infill) {
        translate([0, 0, thickness/2]) {
          if (top_text != "") panel_text(0, 4, top_text, thickness, size=text_size * top_line_scale);
          bottom_features();
        }
      } else {
        difference() {
          linear_extrude(height = thickness) square(tile_size, center=true);
          translate([0, 0, thickness/2]) {
            if (top_text != "") panel_text(0, 4, top_text, thickness, size=text_size * top_line_scale);
            bottom_features();
          }
        }
      }
    }
}

module korry_efis_light_guide(x, y, front_z=0, scale_factor=0.8) {
  base = "../existing_files/airbus-a320-efis-korry-style-switch-model_files/";
  light_guide_stl = str(base, "efis-14mm-x-12mm-korry-ma08-button-light-guide.stl");

  // Its top face (where the indicator+legend tile sits) is already at
  // local z=0, so front_z is used directly with no extra offset.
  extend_by = 2;
  z_cut = -5;
  translate([x, y, front_z])
    scale([scale_factor, scale_factor, scale_factor])
      extend_at(z_cut, extend_by)
        import(light_guide_stl, convexity=10);
}

// TODO: extend gap for switch
module korry_button_light_guide(x, y, front_z=0, scale_factor=0.8) {
  base = "../existing_files/airbus-a320-korry-style-switch-for-3mm-panels-model_files/";
  light_guide_stl = str(base, "20mm-acrylic-dual-led-korry-ma32-1-button-light-guide.stl");

  z_cut = -5;
  extend_by = 2;

  // As above: top face already sits at local z=0.
  difference() {
    translate([x, y, front_z])
      scale([scale_factor, scale_factor, scale_factor])
        extend_at(z_cut, extend_by)
          import(light_guide_stl, convexity=10);
    translate([x-1.5, y-1.0, front_z-18.5])
      cube([3,2,3.7]);
  }
}

// Inserts `extra` mm of extra length at height z_cut, without
// touching either end: everything at/above z_cut (e.g. the flange) is
// kept exactly where it is; everything below z_cut is kept as a
// rigid, unmodified chunk that just slides straight down by `extra`,
// so its own shape survives untouched, only relocated further from
// the fixed side (useful if a real feature -- snap tabs, a glue lip --
// ever needs preserving down there; on the ma32 housing specifically,
// double-checked against the full assembled cross-section rather than
// one half alone, there is no such feature -- the housing is a plain
// hollow tube all the way to its true bottom, so extend_offset=0 is
// the right default there). The new gap between the two chunks is
// bridged by extruding the plain-wall cross-section sampled just
// above the cut (z_cut+epsilon, inside the fixed chunk) -- so this is
// only sane at a height where the wall is a plain, non-tapered
// profile. Takes its geometry as children() so callers can chain
// other modifications (e.g. a groove cut) onto the same STL first.
module extend_at(z_cut, extra) {
  if (extra <= 0) {
    children();
  } else {
    epsilon = 0.05;
    big = 1000;
    union() {
      // Fixed chunk: at/above the cut, untouched in place.
      intersection() {
        children();
        translate([-big/2, -big/2, z_cut])
          cube([big, big, big]);
      }
      // Moving chunk: below the cut, shifted down by `extra` so its
      // shape is preserved exactly, just relocated further away.
      translate([0, 0, -extra])
        intersection() {
          children();
          translate([-big/2, -big/2, -big])
            cube([big, big, big + z_cut]);
        }
      // Filler bridging the new extra-tall gap.
      translate([0, 0, z_cut - extra])
        linear_extrude(height = extra)
          projection(cut = true)
            translate([0, 0, -(z_cut + epsilon)])
              children();
    }
  }
}


// Internal dimensions 11.4 x 9.6
module korry_efis_housing(x, y, front_z=0, scale_factor=0.8, extend_by=4, extend_offset=0, groove_offset=2.5, top_groove_offset=5) {
  base = "../existing_files/airbus-a320-efis-korry-style-switch-model_files/";
  housing_stl = str(base, "efis-14mm-x-12mm-korry-ma08-housing.stl");

  // Same as front_panel.scad's korry_efis_button(): the flange front
  // face sits at local z=2.0 (measured from the STL's bounding box).
  housing_flange_z = 2.0; // raw (pre-scale) flange z
  front_face_z = housing_flange_z * scale_factor;
  housing_z_min = -16.3; // measured bottom-most z of the STL
  z_cut = housing_z_min + extend_offset;

  // Two grooves for the external slide-on clip, both sized for this
  // housing (half_width=8.5): one groove_offset up from the true
  // bottom, one top_groove_offset down from the flange. Checked both
  // target heights via projection(cut) -- z_min+2.5 sits in the
  // housing's more complex mid-section (confirmed a flat wall
  // y=[-5,5] there regardless); flange-5 sits in a simpler plain
  // hollow-tube region closer to the flange, also confirmed flat.
  //
  // groove_offset/top_groove_offset are specified in final, real-world
  // mm (i.e. groove_offset=5 really is 5mm from the bottom in the
  // printed part) -- but the cut itself happens here, before the
  // enclosing scale(scale_factor) below, in the STL's own raw/pre-
  // scale coordinate frame. So the requested real-mm offset has to be
  // converted back to raw units (divided by scale_factor) before it's
  // added to a raw z coordinate, otherwise what you get in the final
  // part is offset*scale_factor, not offset. korry_housing_clip()
  // does the same conversion so its tongue still lands on the groove.
  groove_z = housing_z_min + groove_offset/scale_factor;
  top_groove_z = housing_flange_z - top_groove_offset/scale_factor;

  module housing_body() {
    difference() {
      import(housing_stl, convexity=10);
      if (groove_offset > 0) housing_side_groove_cut(groove_z-2, half_width=8.5);
      if (top_groove_offset > 0) housing_side_groove_cut(top_groove_z, half_width=8.5);
    }
  }

  translate([x, y, front_z - front_face_z])
    scale([scale_factor, scale_factor, scale_factor])
      extend_at(z_cut, extend_by)
        housing_body();
}

// Cuts a shallow groove into the OUTSIDE of the housing's left and
// right (x-facing) walls, centered on groove_z, running the full
// length of those faces in y. This is what the external clip's
// tongues seat into -- not a cavity/internal feature.
//
// Chamfered on the underside only, top edge stays sharp/flat: the
// housing prints upside down, so only the notch's underside (in the
// *printer's* build direction, which is the opposite of this
// module's own +z once flipped) is an overhang that needs a
// self-supporting lead-in -- the top edge is naturally supported from
// below either way, so leaving it sharp costs nothing and keeps a
// crisper mating edge. With chamfer=groove_depth (the default),
// rise==run==groove_depth, i.e. a true 45°. Built as hull() of two
// thin "sheet" rectangles (one at the surface, one at full depth),
// both sharing the same top_z so only the bottom tapers -- hull() of
// two rectangles can't produce a self-intersecting or wrong-winding
// mesh, a hand-built polygon can. The outer sheet sits `epsilon` past
// the housing's true surface so the cut genuinely overlaps material
// there instead of leaving a coincident face with the housing's own
// outer wall (same coincident-face issue hit earlier with the
// internal-cap design, fixed the same way: a real, if tiny, overlap
// rather than an exactly-flush boundary).
module housing_side_groove_cut(groove_z, half_width=11.45, groove_height=2, groove_depth=0.6, chamfer=0.4) {
  epsilon = 0.1;
  chamfer_c = min(chamfer, groove_depth, groove_height);
  top_z = groove_z + groove_height/2; // sharp edge, same at outer and inner sheets
  outer_bottom_z = groove_z - groove_height/2;
  inner_bottom_z = outer_bottom_z + chamfer_c; // chamfered/raised bottom at full depth

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

// One side of the external clip, built for the right (+x) side in
// its own unmirrored frame -- korry_button_housing_clip() mirrors a
// copy for the left side, so sign-juggling only has to happen once.
// A strap sits flush against the housing's outer face; a tongue
// reaches inward from the strap into the groove cut above, stopping
// tongue_clearance short of the groove's inner wall for a sliding
// fit, and overlapping `overlap` into the strap so the two form one
// true volumetric union rather than a flush, coincident face (which
// CGAL reports as non-manifold -- hit this exact issue on the
// previous internal-cap design and fixed it the same way there).
module clip_arm_right(half_width, arm_width, groove_z, groove_height, groove_depth, tongue_clearance, arm_top, arm_bottom, clip_depth, chamfer=0.4) {
  overlap = 0.05;
  arm_center_z = (arm_top + arm_bottom) / 2;
  arm_height = arm_top - arm_bottom;

  translate([half_width + arm_width/2, 0, arm_center_z])
    cube([arm_width, clip_depth, arm_height], center=true);

  // Tongue: chamfered on the underside only (matching
  // housing_side_groove_cut()'s sharp-top/chamfered-bottom shape) --
  // full height where it meets the strap (x=half_width, with a small
  // overlap into the strap to avoid a coincident face there), tapering
  // to a narrower tip as it reaches toward the groove's inner wall,
  // stopping tongue_clearance short of it for a sliding fit. Top edge
  // (top_z) is the same at base and tip so it stays flat/sharp, only
  // the bottom rises. Same hull()-of-two-sheets construction as
  // housing_side_groove_cut(), same reasoning (robust, can't
  // self-intersect).
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

// The external clip itself: slides onto the housing along y (not
// pushed up from below), gripping the outside of the left/right
// walls via tongues that seat in housing_side_groove_cut()'s channel,
// joined by a floor that spans the full width underneath the
// housing's bottom end, covering the entire base opening so the
// internals (PCB, wiring) can't fall out. groove_offset here means
// the same thing as korry_button_housing()/korry_efis_housing()'s
// groove_offset/top_groove_offset: real, final mm from the housing's
// true bottom tip (z=0 in this standalone part's own frame) -- NOT
// raw pre-scale mm. Shared by both housings via the
// korry_button_housing_clip()/korry_efis_housing_clip() wrappers
// below, which just supply each housing's own measured half_width
// (and a narrower clip_depth for the smaller efis one).
module korry_housing_clip(x=0, y=0, scale_factor=0.8, groove_offset=2.5, half_width=11.45, groove_height=2, groove_depth=0.6, tongue_clearance=0.1, arm_width=1.5, arm_top_margin=1.5, clip_depth=10, floor_thickness=1.5, chamfer=0.4) {
  // This clip's own geometry (half_width, arm_width, etc.) is built
  // in raw/full-size units, all scaled together at the very end below
  // -- so, same as the housing modules' groove cut, groove_offset has
  // to be converted from the real-mm value the caller passed in back
  // to raw units before it's used here, or the tongue would land
  // offset*scale_factor mm up instead of offset mm, and no longer
  // match the housing's own (now-fixed) groove position.
  raw_groove_offset = groove_offset / scale_factor;
  arm_top = raw_groove_offset + groove_height/2 + arm_top_margin;
  arm_bottom = -floor_thickness;

  // scale_factor is applied once, uniformly, over the whole part, the
  // same way korry_button_housing()/korry_efis_housing() scale their
  // groove down along with everything else. Without this the clip
  // would render at full size next to an 0.8-scaled housing and
  // visibly not match.
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

// Same mechanism, sized for the smaller efis housing: half_width=8.5
// (measured), clip_depth reduced to 6mm to stay clear of the housing's
// more complex end regions -- projection(cut) showed the flat outer
// wall at x=+-8.5 only runs y=[-5,5] here, narrower than ma32's.
module korry_efis_housing_clip(x=0, y=0, scale_factor=0.8, groove_offset=4, half_width=8.5, groove_height=2, groove_depth=0.6, tongue_clearance=0.1, arm_width=1.5, arm_top_margin=1.5, clip_depth=15, floor_thickness=1.5, chamfer=0.4) {
  korry_housing_clip(x, y, scale_factor, groove_offset, half_width, groove_height, groove_depth, tongue_clearance, arm_width, arm_top_margin, clip_depth, floor_thickness, chamfer);
}


// Internal dimensions 15.12 x 15.12
module korry_button_housing(x, y, front_z=0, scale_factor=0.8, extend_by=2, extend_offset=2, groove_offset=2.5, top_groove_offset=5) {
  base = "../existing_files/airbus-a320-korry-style-switch-for-3mm-panels-model_files/";
  lower_stl = str(base, "20mm-acrylic-dual-led-korry-ma32-2-lower-housing.stl");
  upper_stl = str(base, "20mm-acrylic-dual-led-korry-ma32-3-upper-housing.stl");

  // Same as front_panel.scad's korry_button(): the front face of both
  // parts sits at local z=-3.0 (measured from their bounding boxes).
  front_face_z = -3.0;
  housing_z_min = -32.6; // measured bottom-most z of both STLs
  z_cut = housing_z_min + extend_offset;

  // Two grooves for the external slide-on clip: one groove_offset up
  // from the true bottom, one top_groove_offset down from the flange.
  // Checked both target heights via projection(cut) on a single half
  // -- both land on flat, unbroken wall (no taper) at half_width.
  //
  // Same real-mm-to-raw conversion as korry_efis_housing() -- see its
  // comment for why -- so groove_offset=5 here really means 5mm in
  // the finished part, not 5mm before scaling.
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


if (part == "efis_indicator_legend") {
  korry_efis_indicator_legend(0, 0, top_shape=label_top_shape, bottom_text=label_bottom_text, infill=show_infill);
} else if (part == "button_legend") {
  korry_button_legend(0, 0, top_text=label_top_text, bottom_text=label_bottom_text, bottom_box=label_bottom_box, infill=show_infill);
} else if (part == "efis_light_guide") {
  korry_efis_light_guide(0, 0);
} else if (part == "button_light_guide") {
  korry_button_light_guide(0, 0);
} else if (part == "efis_housing") {
  korry_efis_housing(0, 0);
} else if (part == "button_housing") {
  korry_button_housing(0, 0);
} else if (part == "efis_housing_clip") {
  korry_efis_housing_clip();
} else if (part == "button_housing_clip") {
  korry_button_housing_clip();
} else if (part == "all") {
  // korry_efis_indicator_legend(-3.5*part_spacing, 0, top_shape="lines", bottom_text="A/TH", infill=show_infill);
  // korry_button_legend(-2.5*part_spacing, 0, top_text="MAST", bottom_text="CAUT", bottom_box=true, infill=show_infill);
  // korry_efis_light_guide(-1.5*part_spacing, 0);
  // korry_button_light_guide(-0.5*part_spacing, 0);
  korry_efis_housing(0.5*part_spacing, 0);
  // korry_button_housing(1.5*part_spacing, 0);
  // korry_efis_housing_clip(2.5*part_spacing, 0);
  // korry_button_housing_clip(3.5*part_spacing, 0);
}
