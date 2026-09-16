// diam of fcu knob base 21 mm
// radio 25mm
// knob 21.5
// 7mm shaft
// encoder box 34 x 19.5
// encoder centre at 6.5mm from left
print_template = false;
show_infill = true;
infill_type = "paint"; // [main, paint]
part = "all"; // [main_panel, side_left, side_right, all]

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
    inset = 5; 
    // Position four holes at the corners
    for (x = [inset, panel_width - inset]) {
      for (y = [inset, panel_height - inset]) {
        translate([x0+x, y0+y, -depth/2]) 
          cylinder(d = hole_diameter, h = depth, $fn = global_fn);
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
    for (y = [4,26]) {
      translate([x0+5+slot_y(i),y0+y,z_offset])
        cylinder(5, d=1.5, center=true, $fn = global_fn);
      translate([x0+28+slot_y(i),y0+y,z_offset])
        cylinder(5, d=1.5, center=true, $fn = global_fn);
    }
  }

  translate([x0-12+main_panel_width,y0+20,z_offset])
    cube([1.5,15,mount_depth], center=true);

}

module korry_efis_button_simple(x, y, cut_through=false) {
  extrude = cut_through ? extrude_depth+disperser_panel_depth : extrude_depth;
  start_z = cut_through ? -extrude/2-disperser_panel_depth : -extrude/2;
  r = 2;
  translate([x,y,start_z])
    linear_extrude(height = extrude) {
      offset(r = r) 
        offset(delta = -r) 
          // square([17,15], center=true);
          square([13.6,12], center=true);
    }
}

module korry_efis_button(x, y, cut_through=false, scale_factor=0.8) {
  housing_stl = "existing_files/airbus-a320-efis-korry-style-switch-model_files/efis-14mm-x-12mm-korry-ma08-housing.stl";
  
  // The STL's flange front face is at local z=2.0 (measured from its
  // bounding box). After scaling, shift so that face sits flush with
  // the panel's front face at z = +extrude_depth/2.
  front_face_z = 2.0 * scale_factor;
  
  translate([x, y, extrude_depth/2 - front_face_z])
    scale([scale_factor, scale_factor, scale_factor])
      hull()
        import(housing_stl, convexity=10);
} 

// module korry_ecam_button(x, y) {
//   translate([x,y,0])
//   cube([18.8, 13.8, extrude_depth], center=true);
// }

module korry_button_simple(x, y, cut_through=false) {
  extrude = cut_through ? extrude_depth+disperser_panel_depth : extrude_depth;
  start_z = cut_through ? -extrude/2-disperser_panel_depth : -extrude/2;
  r = 1.6;
  // cube([22.9, 22.9, extrude_depth], center=true);
  translate([x,y,start_z])
    linear_extrude(height = extrude) {
      offset(r = r) 
        offset(delta = -r) 
          square([18.32, 18.32], center=true);
    }
}

module korry_button(x, y, cut_through=false, scale_factor=0.8) {
  base = "existing_files/airbus-a320-korry-style-switch-for-3mm-panels-model_files/";
  lower_stl = str(base, "20mm-acrylic-dual-led-korry-ma32-2-lower-housing.stl");
  upper_stl = str(base, "20mm-acrylic-dual-led-korry-ma32-3-upper-housing.stl");
  
  // Front (visible) face of both parts sits at local z=-3.0 (measured
  // from their bounding boxes). After scaling, shift so that face is
  // flush with the panel front face at z = +extrude_depth/2.
  front_face_z = -3.0;
  
  translate([x, y, extrude_depth/2 - front_face_z*scale_factor])
    scale([scale_factor, scale_factor, scale_factor])
      hull() {
        import(lower_stl, convexity=10);
        import(upper_stl, convexity=10);
      }
}

module rotary(x, y, infill=false, cut_through=false, encoder_d=7.5) {
  extrude = cut_through ? extrude_depth+disperser_panel_depth : extrude_depth;
  start_z = cut_through ? -disperser_panel_depth : 0;
  if (!infill) {
    translate([x,y,start_z])
      cylinder(extrude, d=encoder_d, center=true);
  }

  if (!cut_through && encoder_d == 7.5) {
    translate([x,y,0])
      difference() {
        cylinder(extrude, d=encoder_d+3, center=true);
        cylinder(extrude, d=encoder_d+0, center=true);
      }
  }

  rotary_mount_depth = 3;
  translate([x+6.5,y,-2]) {
    for (i = [-12,12])
      translate([0,i,0]) {
        if (!infill && (print_template || $preview)) {
          translate([0,0,2])
            cylinder(3, d=4.0, center=true, $fn=global_fn);
        }
        if (infill) {
          translate([0,0,-rotary_mount_depth]) {
            difference() {    
                cube([6,6,rotary_mount_depth], center=true);
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

module inset_button_ring(x, y, d = 8, infill=false, cut_through=false) {
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
}

module illuminated_ring(ring_d, degrees) {
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

module fcu_rotary_ring(x, y, ring_d=23, degrees=360, infill=false, cut_through=false, encoder_d=7.5) {
  if (!cut_through) {
    // knobs are 21mm base
    translate([x,y,-extrude_depth/2])
      mirror([1,0,0]) {
        illuminated_ring(ring_d, degrees);
      }
  }

  rotary(x, y, infill=infill, cut_through=cut_through, encoder_d=encoder_d);
}

module panel_text(x, y, text_string, size=2.5, infill=false) {
  translate([x,y,-extrude_depth/2])
    linear_extrude(height = extrude_depth) {
      text(text_string, size=size, halign="center", valign="center", font="Futura");
    }
}

module ring_text(cx, cy, radius, angle, text_string, label_gap=3, line_width=0.6, line_length=4.3, size=2.5, infill=false) {
  x = cx + radius * cos(angle);
  y = cy + radius * sin(angle);

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
  if (!infill) {
    korry_efis_button(center, bottom_button_height, cut_through=cut_through);
    korry_efis_button(center - width/2, bottom_button_height + 16, cut_through=cut_through);
    korry_efis_button(center + width/2, bottom_button_height + 16, cut_through=cut_through);
  }
  fcu_rotary_ring(center - 58, rotary_height, infill=infill, cut_through=cut_through);
  fcu_rotary_ring(center - 31, rotary_height, infill=infill, cut_through=cut_through);
  fcu_rotary_ring(center + 58, rotary_height, infill=infill, cut_through=cut_through);
  // ALT has 15mm shaft
  // Extra shaft is 9mm
  fcu_rotary_ring(center + 31, rotary_height, infill=infill, cut_through=cut_through, encoder_d=15.5);
  if (!infill) {
    korry_efis_button(center- 31, bottom_button_height, cut_through=cut_through);
    korry_efis_button(center+ 31, bottom_button_height, cut_through=cut_through);
    korry_efis_button(center+ 58, bottom_button_height, cut_through=cut_through);
  }

  hdgtrk_offset = 42;
  inset_button_ring(center, hdgtrk_offset, infill=infill, cut_through=cut_through);
  panel_text(center-10, hdgtrk_offset+2, "HDG", infill=infill);
  panel_text(center-10, hdgtrk_offset-2, "TRK", infill=infill);
  panel_text(center+10, hdgtrk_offset+2, "V/S", infill=infill);
  panel_text(center+10, hdgtrk_offset-2, "FPA", infill=infill);

  inset_button_ring(center - 58, bottom_button_height, infill=infill, cut_through=cut_through);
  panel_text(center - 58 + 11, bottom_button_height+2, "SPD", infill=infill);
  panel_text(center - 58 + 11, bottom_button_height-3, "MACH", infill=infill);

  label_radius = 16;
  for (l = [
    [130, "100"],
    [50, "1000"]
  ])
      ring_text(center + 31, rotary_height, label_radius, l[0], l[1], infill=infill);

  // panel_text(center+21, 46, "100", infill=infill);
  // panel_text(center+42, 46, "1000", infill=infill);

  panel_text(center+58, 48, "UP", infill=infill);
  panel_text(center+58, 20, "DOWN", infill=infill);

  if (!infill) {
    korry_left = 168;
    korry_bottom = 18;
    korry_button(center - korry_left, korry_bottom+21, cut_through=cut_through);
    korry_button(center - korry_left, korry_bottom, cut_through=cut_through);
  }

  ldg_center = -149;
  inset_button_ring(center +ldg_center, rotary_height, infill=infill, cut_through=cut_through);
  panel_text(center+ldg_center, rotary_height+12, "LDG", infill=infill);
  panel_text(center+ldg_center, rotary_height+8, "UP", infill=infill);
  panel_text(center+ldg_center, rotary_height-8, "DOWN", infill=infill);

  bar_height = 41;
  bar_offset = 16.8;
  bar_v_offset = 8;
  translate([center-bar_offset,bar_height/2+bar_v_offset,0])
    cube([1,bar_height,extrude_depth], center=true);
  translate([center+bar_offset,bar_height/2+bar_v_offset,0])
    cube([1,bar_height,extrude_depth], center=true);
}

module baro(infill=false, cut_through=false) {
  center = 88;
  // baro encoder is 8mm deep on back
  fcu_rotary_ring(center, rotary_height, encoder_d=15.5, infill=infill, cut_through=cut_through);
  if (!infill) {
    korry_efis_button(center -8, bottom_button_height, cut_through=cut_through);
    korry_efis_button(center +8, bottom_button_height, cut_through=cut_through);
  }
}

module rmp(infill=false, cut_through=false) {
  center = 55;
  fcu_rotary_ring(center, rotary_height, ring_d = 27, infill=infill, cut_through=cut_through);
  if (!infill) {
    korry_efis_button(center, bottom_button_height, cut_through=cut_through);
  }
}

module efis(panel_start_x, panel_width, infill=false, cut_through=false) {
  center = panel_start_x + panel_width/2;
  button_height = 55;
  efis_rotary_height = rotary_height - 5;
  if (!infill) {
    for (i=[-2:2]) {
      korry_efis_button(center - i*15, button_height, cut_through=cut_through);  
    }
  }
  
  rotary_offset = 18;
  rotary_shift = 6;
  for (i=[-1,1]) {
    fcu_rotary_ring(center - i*rotary_offset-rotary_shift, efis_rotary_height, degrees=i==1?180:225, infill=infill, cut_through=cut_through);
    inset_button_ring(center - i*rotary_offset-rotary_shift, bottom_button_height, infill=infill, cut_through=cut_through);
    for (j=[-1,1]) {
      panel_text(center - i*rotary_offset-rotary_shift + j*10, bottom_button_height, j == -1 ? "ADF" : "VOR", infill=infill);
      panel_text(center - i*rotary_offset-rotary_shift, bottom_button_height + j*7, j == -1 ? "OFF" : (i == 1 ? "1" : "2"), infill=infill);
    }
  }

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
    [0, "PL"],
  ])
      ring_text(center-rotary_offset-rotary_shift, efis_rotary_height, label_radius, l[0], l[1], infill=infill);
}

module ecam(panel_start_x, panel_width, infill=false, cut_through=false) {
  center = panel_start_x + panel_width/2;
  button_height = 55;
  button_height2 = button_height -13;
  if (!infill) {
    for (i=[-2:2]) {
      korry_efis_button(center - i*15, button_height, cut_through=cut_through);
      korry_efis_button(center - i*15, button_height2, cut_through=cut_through);
    }
    korry_button(center -28, 15, cut_through=cut_through);
    korry_button(center -8, 15, cut_through=cut_through);
  }
}

module main_panel(infill = false) {
  if (infill) {
    fcu(infill);
    baro(infill);
    rmp(infill);
    if (part == "side_left" || part == "all") {
      efis(-90, 90, infill=infill);
    }
    if (part == "side_right" || part == "all") {
      ecam(main_panel_width, 90, infill=infill);
    }
    difference() {
      union() {
        panel(depth=disperser_panel_depth, panel_height=50, z0=-(panel_depth/2+disperser_panel_depth/2));
        if (part == "side_left" || part == "all") {
          panel(90, 80, x0=-90, depth=disperser_panel_depth, z0=-(panel_depth/2+disperser_panel_depth/2));
        }
        if (part == "side_right" || part == "all") {
          panel(90, 80, x0=main_panel_width, depth=disperser_panel_depth, z0=-(panel_depth/2+disperser_panel_depth/2)); // orientation="right",
        }
      }
      fcu(cut_through=true);
      baro(cut_through=true);
      rmp(cut_through=true);
      if (part == "side_left" || part == "all") {
        efis(-90, 90, cut_through=true);
      }
      if (part == "side_right" || part == "all") {
        ecam(main_panel_width, 90, cut_through=true);
      }
    }
  } else {
    difference() {
      union() {
        panel();
        rear_mount(3.5,49);
        if (part == "side_left" || part == "all") {
          panel(90, 80, x0=-90);
        }
        if (part == "side_right" || part == "all") {
          panel(90, 80, x0=main_panel_width);//, orientation="right");
        } 
      }
      front_windows(3.5,49);
      if (print_template || $preview) {
        rear_mount(3.5,49,z0=3);
      }
      fcu();
      baro();
      rmp();
      if (part == "side_left" || part == "all") {
        efis(-90, 90);
      }
      if (part == "side_right" || part == "all") {
        ecam(main_panel_width, 90);
      }
    }
  }
}

if (part == "main_panel") {
  main_panel();
} else if (part == "infill") {
  main_panel(infill=true);
} else {
  if (!show_infill) {
    main_panel();
  } else {
    main_panel(infill=true);
  }
}

