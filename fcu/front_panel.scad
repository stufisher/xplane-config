// diam of fcu knob base 21 mm
// radio 25mm
// knob 21.5
// 7mm shaft
// encoder box 34 x 19.5
// encoder centre at 6.5mm from left
print_template = false;
show_infill = false;
infill_type = "all"; // [all, slice]
part = "main_panel"; // [main_panel, side_left, side_right, all]

wall           = 2;
n_screens = 8;
window_w         = 25;   // front cutout width (mm)
window_h         = 14;   // front cutout height (mm) (actually 18mm display, but bottom is pcb)
                         // from original cutout (18mm), to bottom of oledd pcb is +7mm
window_top_gap   = 4;    // board top edge -> top of window (mm), clears header strip
//window_bottom_gap = 18 + 7;
window_bottom_gap = 23;

board_w          = 33;   // board width, left-right in the row (mm)
board_h          = 28;   // board height, bottom (notch) to top (header) (mm)

grid_pitch = 2.54; // stripboard hole spacing (mm)
gap_holes  = [13, 13, 14, 11, 11, 11, 11];

main_panel_width = 260;
main_panel_height = 80;
side_panel_width = 100;
side_panel_height = main_panel_height;
panel_depth = 3;
disperser_panel_depth = 2;

// to cover panel depth
extrude_depth = panel_depth;

global_fn = 32;

module panel(panel_width = main_panel_width, panel_height = main_panel_height, x0 =0, y0 =0, z0=0, depth=panel_depth) {
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

module panel_edge(panel_width=main_panel_width, panel_height=main_panel_height, x0=0, y0=0, z0=0, depth=panel_depth) {
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

module panel_cut(panel_width = main_panel_width, panel_height = main_panel_height, x0 =0, y0 = 0, orientation="left", z0=0, depth=panel_depth) {
  difference() {
    panel(panel_width, panel_height, x0, y0, depth=depth, z0=z0);
    cut_panel_height = 25;
    cut_panel_width = panel_width * 1.5;
    rotation_angle = 10;
    cut_panel_adj = cos(rotation_angle) * panel_width;
    cut_panel_opp = sin(rotation_angle) * panel_width;
    translate([x0 + cut_panel_adj/2, y0 + panel_height + cut_panel_height/2 - cut_panel_opp/2, z0-2])
      rotate([0,0,orientation == "left" ? rotation_angle : -rotation_angle])
        linear_extrude(height = panel_depth+1) {
            square([cut_panel_width,cut_panel_height], center=true);
        }
  }
}

function cumul_gap(i) = (i <= 0) ? 0 : cumul_gap(i-1) + gap_holes[i-1]*grid_pitch;
function slot_y(i)  = 3 + cumul_gap(i);

module window_cutter(x0) {
  translate([x0 + (board_w-window_w)/2, board_h - window_top_gap - window_h, -extrude_depth/2])
    cube([window_w, window_h, extrude_depth]);
}

module front_windows(x, y) {
  translate([x,y,0])
    for (i = [0:n_screens-1])
      window_cutter(slot_y(i));
  
  if ($preview) {
    bottom_offset = y + board_h - window_top_gap - window_h - (window_bottom_gap - window_h);
    translate([x,bottom_offset,0])
      cube([250, 1, extrude_depth]);
    }
}

module rear_mount(x0, y0, z0=0) {
  mount_depth = 4;
  z_offset = z0-panel_depth/2-mount_depth/2;
  translate([x0+4,y0+20,z_offset])
    cube([1.5,15,mount_depth], center=true);
  for (i = [1,3,6]) {
    for (y = [3,27]) {
      translate([x0+5+slot_y(i),y0+y,z_offset])
        cylinder(5, d=1.5, center=true, $fn = global_fn);
      translate([x0+28+slot_y(i),y0+y,z_offset])
        cylinder(5, d=1.5, center=true, $fn = global_fn);
    }
  }

  translate([x0-12+main_panel_width,y0+20,z_offset])
    cube([1.5,15,mount_depth], center=true);
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

module korry_efis_button(x, y, cut_through=false, infill=false, scale_factor=0.8) {
  housing_stl = "existing_files/airbus-a320-efis-korry-style-switch-model_files/efis-14mm-x-12mm-korry-ma08-housing.stl";
  
  // The STL's flange front face is at local z=2.0 (measured from its
  // bounding box). After scaling, shift so that face sits flush with
  // the panel's front face at z = +extrude_depth/2.
  front_face_z = 2.0 * scale_factor;
  
  x_growth = cut_through ? 13.8 / 13.6 : 1;
  y_growth = cut_through ? 12.2 / 12 : 1;
  if (!infill) {    
    // translate([x, y, extrude_depth/2 - front_face_z])
    translate([x, y, cut_through ? 2 : -3.2])
      scale([x_growth, y_growth, 1])
        scale([scale_factor, scale_factor, scale_factor])
          hull()
            import(housing_stl, convexity=10);

    // label is 11.2 x 9.6
    r = 0.6;
    translate([x, y, -extrude_depth/2]) {
      linear_extrude(height = extrude_depth) {
        offset(r = r) 
          offset(delta = -r) 
            square([11.55,9.95], center=true);
      }
    }
  }

  if (infill) {
    housing_half_width = 8.5;
    tab_width = 1;
    tab_depth = 5;
    z_offset = -(panel_depth/2+disperser_panel_depth/2) - disperser_panel_depth/2  -tab_depth/2;
    half_width = housing_half_width * scale_factor * x_growth;
    // tabs to match housings
    translate([x+half_width+tab_width/2, y, z_offset]) {
      cube([1,half_width*1.5,tab_depth], center=true);
    }
    translate([x-half_width-tab_width/2, y, z_offset]) {
      cube([1,half_width*1.5,tab_depth], center=true);
    }
    korry_housing_tongues(x, y, half_width, scale_factor, cut_through, -3.2, half_width*1.5);
  }
} 


module korry_button(x, y, cut_through=false, infill=false, scale_factor=0.8) {
  base = "existing_files/airbus-a320-korry-style-switch-for-3mm-panels-model_files/";
  lower_stl = str(base, "20mm-acrylic-dual-led-korry-ma32-2-lower-housing.stl");
  upper_stl = str(base, "20mm-acrylic-dual-led-korry-ma32-3-upper-housing.stl");
  
  // Front (visible) face of both parts sits at local z=-3.0 (measured
  // from their bounding boxes). After scaling, shift so that face is
  // flush with the panel front face at z = +extrude_depth/2.
  front_face_z = -3.0;
  growth = cut_through ? 18.52 / 18.32 : 1;
  
  if (!infill) {
    // translate([x, y, extrude_depth/2 - front_face_z*scale_factor])
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
    x_offset = 0.3;
    translate([x+half_width+tab_width/2, y, z_offset]) {
      cube([1,half_width*1.5,tab_depth], center=true);
    }
    translate([x-half_width-tab_width/2, y, z_offset]) {
      cube([1,half_width*1.5,tab_depth], center=true);
    }
    korry_housing_tongues(x, y, half_width, scale_factor, cut_through, -3.0, half_width*1.5);
  }
  
}

module rotary(x, y, infill=false, cut_through=false, encoder_d=7.5, symmetric_mounts=false, inset=false, rotary_mount_depth=3, extended=true, horizontal=false) {
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
  mount_bosses(x,y, infill=infill, symmetric_mounts=symmetric_mounts, rotary_mount_depth=rotary_mount_depth, extended=extended, horizontal=horizontal);
}

module mount_bosses(x, y, infill=false, symmetric_mounts=false, horizontal=false, spacing=12, rotary_mount_depth=5, extended=true) {
  x_offset = symmetric_mounts ? 0 : 8.2;
  x_extend = extended ? 8 : 0;
  translate([x+x_offset,y,-2]) {
    for (i = [-spacing,spacing])
      translate([horizontal ? i : 0, horizontal ? 0 : i,0]) {
        if (!infill && (print_template || $preview)) {
          translate([0,0,2])
            cylinder(3, d=4.0, center=true, $fn=global_fn);
        }
        if (infill) {
          translate([0,0,-rotary_mount_depth/2-1.5]) {
            difference() {    
                translate([-x_extend/2,0,0])
                  cube([6.5 + x_extend,6.5,rotary_mount_depth], center=true);
                cylinder(rotary_mount_depth, d=4.0, center=true, $fn=global_fn);
            }
          }
        }
      }
    
    // rotate([0,0,90])
    //   translate([0,-12,0])
    //     import("existing_files/SL3_Push-Pull_Rotary_knob_Mark3/SL3_Push-Pull_Mk3_bottom_plate.stl");
  }
}

module inset_button(x, y, d = 8, cut_through=false) {
  extrude = cut_through ? extrude_depth+disperser_panel_depth : extrude_depth;
  start_z = cut_through ? -disperser_panel_depth : 0;
  translate([x,y,start_z])
    cylinder(extrude, d=d, center=true);
}

module inset_button_ring(x, y, d = 8, infill=false, cut_through=false, horizontal=true, bosses=true) {
  if (!cut_through) {
    translate([x,y,0])
      difference() {
        cylinder(extrude_depth, d=d+2.5, center=true);
        cylinder(extrude_depth, d=d+1.0, center=true);
      }
  }

  if (!infill) {
    inset_button(x, y, cut_through=cut_through);
  }
  if (bosses) {
    mount_bosses(x, y, infill=infill, symmetric_mounts=true, horizontal=horizontal, spacing=8, extended=false);
  }
}

module _illuminated_ring(ring_d, degrees) {
  difference() {
    // cylinder(extrude_depth, d=ring_d+1.5, center=true);
    rotate_extrude(angle = degrees, $fn = global_fn) {
        square([(ring_d+2.0)/2, extrude_depth]);
    }
    // cylinder(extrude_depth, d=ring_d, center=true);
    rotate_extrude(angle = degrees, $fn = global_fn) {
        square([ring_d/2, extrude_depth]);
    }
  }
}

module illuminated_ring(ring_d, degrees) {
  rotate_extrude(angle = degrees, $fa = 2, $fs = 0.5)
    translate([ring_d/2, 0]) square([1.0, extrude_depth]);
}

module fcu_rotary_ring(x, y, ring_d=23, degrees=360, infill=false, cut_through=false, encoder_d=7.5, symmetric_mounts=false, inset=false, rotary_mount_depth=3, extended=true, horizontal=false) {
  if (!cut_through) {
    // knobs are 21mm base
    translate([x,y,-extrude_depth/2])
      mirror([1,0,0]) {
        illuminated_ring(ring_d, degrees);
      }
  }

  rotary(x, y, infill=infill, cut_through=cut_through, encoder_d=encoder_d, symmetric_mounts=symmetric_mounts, inset=inset, rotary_mount_depth=rotary_mount_depth, extended=extended, horizontal=horizontal);
}

module panel_text(x, y, text_string, size=3.2, infill=false) {
  translate([x,y,-extrude_depth/2])
    linear_extrude(height = extrude_depth) {
      offset(delta = 0.15)
        text(text_string, size=size, halign="center", valign="center", font="Futura", spacing=1.1);
        // text(text_string, size=size, halign="center", valign="center", font="Arial");
    }
}

module ring_text(cx, cy, radius, angle, text_string, label_gap=3, line_width=0.6, line_length=4.3, size=3.2, infill=false) {
  text_offset = 1.05;
  x = cx + radius * cos(angle) * text_offset;
  y = cy + radius * sin(angle) * text_offset;

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

rotary_height = 34;
bottom_button_height = 11;

module fcu(infill=false, cut_through=false) {
  center = 180;
  width = 16;
  outer1 = 32.5;
  outer2 = 61.5;
  korry_efis_button(center, bottom_button_height, infill=infill, cut_through=cut_through);
  korry_efis_button(center - width/2, bottom_button_height + 16, infill=infill, cut_through=cut_through);
  korry_efis_button(center + width/2, bottom_button_height + 16, infill=infill, cut_through=cut_through);
  mount_bosses(center, bottom_button_height+16, infill=infill, spacing=19, symmetric_mounts=true, extended=false, horizontal=true);
  mount_bosses(center, bottom_button_height, infill=infill, spacing=11, symmetric_mounts=true, extended=false, horizontal=true);

  fcu_rotary_ring(center - outer2, rotary_height, infill=infill, cut_through=cut_through, inset=true, encoder_d=10, rotary_mount_depth=8);
  fcu_rotary_ring(center - outer1, rotary_height, infill=infill, cut_through=cut_through, inset=true, encoder_d=10, rotary_mount_depth=8);
  fcu_rotary_ring(center + outer2, rotary_height, infill=infill, cut_through=cut_through, inset=true, encoder_d=10, rotary_mount_depth=8);
  // ALT has 15mm shaft
  // Extra shaft is 9mm
  fcu_rotary_ring(center + outer1, rotary_height, infill=infill, cut_through=cut_through, encoder_d=15.2, rotary_mount_depth=7);

  korry_efis_button(center- outer1, bottom_button_height, infill=infill, cut_through=cut_through);
  mount_bosses(center - outer1, bottom_button_height, infill=infill, spacing=11, symmetric_mounts=true, extended=false, horizontal=true);
  korry_efis_button(center+ outer1, bottom_button_height, infill=infill, cut_through=cut_through);
  korry_efis_button(center+ outer2, bottom_button_height, infill=infill, cut_through=cut_through);

  hdgtrk_offset = 42;
  inset_button_ring(center, hdgtrk_offset, infill=infill, cut_through=cut_through);
  panel_text(center-10.5, hdgtrk_offset+2.2, "HDG", infill=infill);
  panel_text(center-10.5, hdgtrk_offset-2.2, "TRK", infill=infill);
  panel_text(center+10, hdgtrk_offset+2.2, "V/S", infill=infill);
  panel_text(center+10, hdgtrk_offset-2.2, "FPA", infill=infill);

  inset_button_ring(center - outer2, bottom_button_height, infill=infill, cut_through=cut_through);
  panel_text(center - outer2 + 12.5, bottom_button_height+2, "SPD", infill=infill);
  panel_text(center - outer2 + 12.5, bottom_button_height-3, "MACH", infill=infill);

  right_button_offset = 14.6;
  inset_button_ring(center + outer2 - right_button_offset, bottom_button_height+2, infill=infill, cut_through=cut_through, horizontal=false);
  panel_text(center + outer2 - right_button_offset, bottom_button_height-5.5, "METRIC", infill=infill);
  mount_bosses(center + outer2 - right_button_offset, bottom_button_height, infill=infill, spacing=25, symmetric_mounts=true, extended=false, horizontal=true);

  label_radius = 16;
  for (l = [
    [130, "100"],
    [50, "1000"]
  ])
      ring_text(center + outer1, rotary_height, label_radius, l[0], l[1], infill=infill);

  panel_text(center+outer2, 48.5, "UP", infill=infill);
  panel_text(center+outer2, 19.4, "DOWN", infill=infill);

  korry_left = 164;
  korry_bottom = 14;
  korry_button(center - korry_left, korry_bottom, cut_through=cut_through, infill=infill);
  korry_button(center - korry_left + 20, korry_bottom, cut_through=cut_through, infill=infill);
  mount_bosses(center - korry_left + 18.5, bottom_button_height, infill=infill, spacing=32, symmetric_mounts=true, extended=false, horizontal=true);

  ldg_center = -157;
  ldg_height = rotary_height + 5;
  inset_button_ring(center +ldg_center, ldg_height, infill=infill, cut_through=cut_through);
  // panel_text(center+ldg_center, ldg_height+12, "LDG", infill=infill);
  panel_text(center+ldg_center, ldg_height+8, "UP", infill=infill);
  panel_text(center+ldg_center, ldg_height-8, "DOWN", infill=infill);

  bar_height = 44;
  bar_offset = 16.9;
  bar_v_offset = 5.5;
  translate([center-bar_offset,bar_height/2+bar_v_offset,0])
    cube([1,bar_height,extrude_depth], center=true);
  translate([center+bar_offset,bar_height/2+bar_v_offset,0])
    cube([1,bar_height,extrude_depth], center=true);
}

module baro(infill=false, cut_through=false) {
  center = 88;
  // baro encoder is 8mm deep on back
  fcu_rotary_ring(center, rotary_height, encoder_d=15.2, infill=infill, cut_through=cut_through, rotary_mount_depth=7);
  korry_efis_button(center -8, bottom_button_height, infill=infill, cut_through=cut_through);
  korry_efis_button(center +8, bottom_button_height, infill=infill, cut_through=cut_through);

  bar_height = 44;
  bar_offset = 16.;
  bar_v_offset = 5.5;
  translate([center-bar_offset,bar_height/2+bar_v_offset,0])
    cube([1,bar_height,extrude_depth], center=true);
  translate([center+bar_offset-0.2,bar_height/2+bar_v_offset,0])
    cube([1,bar_height,extrude_depth], center=true);
}

module rmp(infill=false, cut_through=false) {
  center = 55.7;
  fcu_rotary_ring(center, rotary_height, ring_d = 27, infill=infill, cut_through=cut_through, symmetric_mounts=true, extended=false, horizontal=true, rotary_mount_depth=5);
  korry_efis_button(center, bottom_button_height, infill=infill, cut_through=cut_through);
}

module efis(panel_start_x, panel_width, infill=false, cut_through=false) {
  center = panel_start_x + panel_width/2;
  button_height = 70;
  efis_rotary_height = rotary_height + 6;
  for (i=[-2:2]) {
    korry_efis_button(center - i*15, button_height, infill=infill, cut_through=cut_through);  
  }
  panel_text(center - 36.5, efis_rotary_height+18, "ROSE", infill=infill);
  if (!cut_through) {
    translate([center - rotary_offset-rotary_shift,efis_rotary_height,-panel_depth/2])
      difference() {
        rotate([0,0,90]) {
          illuminated_ring(44, 90);
        }
        // rotate([0,0,114]) {
        //   illuminated_ring(44, 23);
        // }
        rotate([0,0,114]) {
          rotate_extrude(angle = 23, $fa = 2, $fs = 0.5)
            translate([44/2 - 0.5, -0.5]) square([1.0 + 1, extrude_depth + 1]);
        }
      }
  }
  
  rotary_offset = 23;
  rotary_shift = 0;
  for (i=[-1,1]) {
    fcu_rotary_ring(center - i*rotary_offset-rotary_shift, efis_rotary_height, degrees=i==1?180:225, infill=infill, cut_through=cut_through, symmetric_mounts=true, horizontal=true, extended=false, rotary_mount_depth=5, encoder_d=9.5);
  }

  switch_height = efis_rotary_height - 19;
  switch_shift = 32;
  switch_offset = 7.5;
  for (i=[-1,1]) {
    inset_button_ring(center - switch_shift, i*switch_offset+switch_height, infill=infill, cut_through=cut_through, bosses=false);
    panel_text(center - switch_shift - 8, i*switch_offset+switch_height, i == -1 ? "1" : "2", infill=infill);
  }
  for (j=[-1,1]) {
    panel_text(center - switch_shift + j*9.5, switch_offset+switch_height-8, j == -1 ? "ADF" : "VOR", infill=infill);
  }
  panel_text(center - switch_shift, switch_offset+switch_height - 23.5, "OFF", infill=infill);

  label_radius = 16;
  for (l = [
    [180, "10"],
    [135, "20"],
    [90,  "40"],
    [45, "80"],
    [0, "160"],
    [-45, "320"]
  ])
      ring_text(center+rotary_offset-rotary_shift, efis_rotary_height, label_radius, l[0], l[1], infill=infill);
  for (l = [
    [180, "LS"],
    [135, "VOR"],
    [90,  "NAV"],
    [45, "ARC"],
    [0, "PLA"],
  ])
      ring_text(center-rotary_offset-rotary_shift, efis_rotary_height, label_radius, l[0], l[1], infill=infill);

  korry_offset = 17;
  korry_button(center + korry_offset, 14, infill=infill, cut_through=cut_through);
  korry_button(center + korry_offset + 20, 14, infill=infill, cut_through=cut_through);

  // pitch trim
  pitch_height = 21;
  fcu_rotary_ring(center - 4, pitch_height, infill=infill, cut_through=cut_through, encoder_d=7.5, rotary_mount_depth=5, ring_d=18, symmetric_mounts=true, extended=false);
  panel_text(center - 4, pitch_height + 13, "+", infill=infill);
  panel_text(center - 4, pitch_height - 13, "-", infill=infill);
  panel_text(center - 4, pitch_height - 17, "PITCH", infill=infill);
}

module ecam(panel_start_x, panel_width, infill=false, cut_through=false) {
  center = panel_start_x + panel_width/2;
  button_height = 70;
  button_height2 = button_height -13;
  for (i=[-3:2]) {
    korry_efis_button(center - i*15 - 7.5, button_height, infill=infill, cut_through=cut_through);
    korry_efis_button(center - i*15 - 7.5, button_height2, infill=infill, cut_through=cut_through);
  }

  wx_rotary = 25;
  wx_rotary_height = 31;
  label_radius = 15.5;
  for (l = [
    [180, "WX"],
    [135, "WX+T"],
    [90,  "TURB"],
    [45, "MAP"],
  ])
      ring_text(center - wx_rotary, wx_rotary_height, label_radius, l[0], l[1], infill=infill);
    fcu_rotary_ring(center - wx_rotary, wx_rotary_height, infill=infill, cut_through=cut_through, degrees=137, rotary_mount_depth=5, ring_d=20, symmetric_mounts=true, horizontal=true, extended=false, encoder_d=9.5);

  wx_switch_offset = 18;
  wx_switch = 13;
  inset_button_ring(center - wx_rotary - wx_switch, wx_rotary_height - wx_switch_offset, infill=infill, cut_through=cut_through, bosses=false);
  panel_text(center - wx_rotary - wx_switch - 7.5, wx_rotary_height - wx_switch_offset, "O", infill=infill);
  for (j=[-1,1]) {
    panel_text(center - wx_rotary - wx_switch, wx_rotary_height - wx_switch_offset+ j*8, j == -1 ? "1" : "2", infill=infill);
  }

  tcas_rotary = -20;
  // tcas_switch_height = 13;
  // tcas_switch_shift = -27;
  // tcas_switch_separation = 12;
  tcas_label_radius = 15.5;
  for (l = [
    [180, "SBY"],
    [135, "ALT"],
    [90,  "XPND"],
    [45, "TA"],
    [0, "T/RA"],
  ])
      ring_text(center - tcas_rotary, wx_rotary_height, tcas_label_radius, l[0], l[1], infill=infill);
    fcu_rotary_ring(center - tcas_rotary, wx_rotary_height, infill=infill, cut_through=cut_through, degrees=180, rotary_mount_depth=5, ring_d=20, symmetric_mounts=true, horizontal=true, extended=false, encoder_d=9.5);

  prk_center = -20;
  prk_height = wx_rotary_height - wx_switch_offset;
  inset_button_ring(center + prk_center, prk_height, infill=infill, cut_through=cut_through, bosses=false);
  panel_text(center + prk_center - 8.5, prk_height, "PK", infill=infill);
  panel_text(center + prk_center, prk_height+8, "ON", infill=infill);
  panel_text(center + prk_center, prk_height-8, "OFF", infill=infill);

  korry_bottom = 12;
  korry_button(center + 36, korry_bottom, cut_through=cut_through, infill=infill);
  korry_button(center + 16, korry_bottom, cut_through=cut_through, infill=infill);
  korry_button(center - 4, korry_bottom, cut_through=cut_through, infill=infill);

  korry_text = 11;
  panel_text(center - 4, korry_bottom + korry_text, "LO", infill=infill);
  panel_text(center + 16, korry_bottom + korry_text, "MED", infill=infill);
  panel_text(center + 36, korry_bottom + korry_text, "FAN", infill=infill);

  bar_height = 23;
  bar_offset = 5.5;
  bar_v_offset = 26;
  translate([center-bar_offset,bar_height/2+bar_v_offset,0])
    cube([1,bar_height,extrude_depth], center=true);
}

module main_panel(infill = false) {
  if (infill) {
    if (part == "main_panel" || part == "all") {
      fcu(infill);
      baro(infill);
      rmp(infill);
    }
    if (part == "side_left" || part == "all") {
      efis(-side_panel_width, side_panel_width, infill=infill);
    }
    if (part == "side_right" || part == "all") {
      ecam(main_panel_width, side_panel_width, infill=infill);
    }
    difference() {
      union() {
        if (part == "main_panel" || part == "all") {
          panel(depth=disperser_panel_depth, panel_height=50-3, panel_width=main_panel_width-4, x0=2, y0=2, z0=-(panel_depth/2+disperser_panel_depth/2));
          panel_edge(panel_height=50-3, panel_width=main_panel_width-4, x0=2, y0=2, z0=-(panel_depth/2+disperser_panel_depth/2)-2.5);
        }
        if (part == "side_left" || part == "all") {
          panel(side_panel_width, side_panel_height, x0=-side_panel_width, depth=disperser_panel_depth, z0=-(panel_depth/2+disperser_panel_depth/2));
        }
        if (part == "side_right" || part == "all") {
          panel(side_panel_width, side_panel_height, x0=main_panel_width, depth=disperser_panel_depth, z0=-(panel_depth/2+disperser_panel_depth/2)); // orientation="right",
        }
      }
      if (part == "main_panel" || part == "all") {
        fcu(cut_through=true);
        baro(cut_through=true);
        rmp(cut_through=true);
      }
      if (part == "side_left" || part == "all") {
        efis(-side_panel_width, side_panel_width, cut_through=true);
      }
      if (part == "side_right" || part == "all") {
        ecam(main_panel_width, side_panel_width, cut_through=true);
      }
    }
  } else {
    difference() {
      union() {
        if (part == "main_panel" || part == "all") {
          panel();
        }
        if (!print_template && part == "main_panel" || part == "all") {
          rear_mount(3.5,49);
        }
        if (part == "side_left" || part == "all") {
          panel(side_panel_width, side_panel_height, x0=-side_panel_width);
        }
        if (part == "side_right" || part == "all") {
          panel(side_panel_width, side_panel_height, x0=main_panel_width, depth=$preview ? 2 : panel_depth);//, orientation="right");
        } 
      }
      front_windows(3.5,49);
      if (print_template || $preview) {
        rear_mount(3.5,49,z0=3);
      }
      if (part == "main_panel" || part == "all") {
        fcu();
        baro();
        rmp();
      }
      if (part == "side_left" || part == "all") {
        efis(-side_panel_width, side_panel_width);
      }
      if (part == "side_right" || part == "all") {
        ecam(main_panel_width, side_panel_width);
      }
    }
  }
}

module main_panel_infill_front_slice(slice_depth=0.4) {
  front_z = disperser_panel_depth - 0.5;
  intersection() {
    main_panel(infill=true);
    translate([-1000, -1000, front_z - slice_depth])
      cube([2000, 2000, slice_depth]);
  }
}

module main_panel_infill_back(slice_depth=0.4) {
  front_z = disperser_panel_depth - 0.5;
  intersection() {
    main_panel(infill=true);
    translate([-1000, -1000, -1000])
      cube([2000, 2000, 1000 + front_z - slice_depth]);
  }
}


if (show_infill) {
  if (infill_type == "slice") {
    main_panel_infill_front_slice();
  } else {
    main_panel_infill_back();
  }
} else {
  main_panel();
}