// Simple box the overhead panel drops into. The panel and its full-size
// diffuser sit flush with the rim on a ledge round the edge and are held by
// M3 self-tapping screws through the corner holes into corner blocks.
// z = 0 is the panel's front face; the box prints open side up.
part = "enclosure"; // [enclosure, pcbs, chips] - pcbs/chips are viewer stand-ins

// Panel numbers, must match oh_panel.scad
panel_width = 246;
panel_height = 110;
panel_depth = 3;
diffuser_depth = 2;   // runs to the panel edges
hole_inset = 4;       // panel corner holes

depth = 38;           // overall, panel front to box back
wall = 2.5;
floor_t = 2.5;
clearance = 0.3;      // panel to pocket wall, each side
ledge = 2;            // diffuser overlap on the ledge
ledge_t = 2;

// Corner blocks
block = 9;            // reaches this far in from the panel edges
block_h = 10;         // solid depth below the diffuser before the 45 deg underside
screw_hole = [2.8, 3.4]; // oval M3 self-tap hole (x, y), not too tight
screw_depth = 7;

// USB-B cutout, right wall: square shell + clearance - VERIFY against the connector
usb_w = 12.5;         // across (Y)
usb_h = 11.5;         // tall (Z)
usb_y = 65;           // clears the ANTI ICE ENG korry below it (housing reaches Y ~55.7)
usb_z = -(depth - floor_t) + usb_h/2; // flush against the inner face of the floor (base)

// Electronics on the floor, clear of the korries (backs ~7.9 mm above the
// floor): MCPs and ESP under EXT LT (toggle lugs ~16.5 mm), TLC under ENG.
// Positions are each board's lower-left corner in panel X/Y.
board_lift = 2.5;     // floor to PCB underside, room for clipped pin tails
pcb_t = 1.6;
board_gap = 0.3;      // board outline to cradle wall
cradle_wall = 1.2;
clip_w = 6;           // clip wall width at each end
clip_lip = 0.5;       // overhang onto the board's top face
corner_arm = 4;       // L-shaped locating corners
// HW-839 MCP23017 breakout, no holes: clip cradle, pads run along the 26 mm edges
mcp_size = [21, 26];
mcp_toggle_x = [40, 63, 86]; // EXT LT toggle columns; pin rows land either side of the toggle body
mcp_pos = [for (x = mcp_toggle_x) [x - mcp_size[0]/2, 10]];
// Adafruit TLC5947: clip cradle, clips on the long edges, headers on the short ends stay clear
tlc_size = [50.8, 25.4];
// Centred in the ENG section (x 129.5-185.5), cradle ~0.5 mm under the
// top-row korry housings (bottom edge y 75.64)
tlc_pos = [157.5 - tlc_size[0]/2, 48.2];
// ESP32-S3 SuperMini, size varies by maker - VERIFY; USB-C end left open, facing -X
// so the plug clears the TLC cradle
esp_size = [18, 24];  // local: USB at the +Y end
// Lower-left corner of the footprint: over the upper APU korry (top edge
// y 52.16), under the top-row korries (bottom edge y 75.64), 6 mm left of the
// APU column to clear the TLC
esp_pos = [114.25 - 6 - esp_size[1]/2, (52.16 + 75.64)/2 - esp_size[0]/2];

$fn = 48;

W = panel_width;
H = panel_height;
stack = panel_depth + diffuser_depth; // panel + diffuser thickness
stack_back = -stack;

module shell() {
  difference() {
    translate([-clearance - wall, -clearance - wall, -depth])
      cube([W + 2*(clearance + wall), H + 2*(clearance + wall), depth]);
    // Pocket for panel + diffuser, panel front flush with the rim
    translate([-clearance, -clearance, stack_back])
      cube([W + 2*clearance, H + 2*clearance, stack + 1]);
    // Opening through the ledge
    translate([ledge, ledge, stack_back - ledge_t - 1])
      cube([W - 2*ledge, H - 2*ledge, ledge_t + 2]);
    // Main cavity below the ledge, narrowing at 45 deg into the ledge opening
    // so the ledge's underside prints without support
    ledge_in = ledge + clearance;
    ledge_bot = stack_back - ledge_t;
    hull() {
      translate([-clearance, -clearance, -depth + floor_t])
        cube([W + 2*clearance, H + 2*clearance, ledge_bot - ledge_in - (-depth + floor_t)]);
      translate([ledge, ledge, ledge_bot - 0.01])
        cube([W - 2*ledge, H - 2*ledge, 0.02]);
    }
    // USB-B cutout through the right wall, above the ANTI ICE ENG korry and
    // flush with the floor so a panel-mount jack's body doesn't need depth
    // past the back of the case
    translate([W + clearance - 2, usb_y - usb_w/2, usb_z - usb_h/2])
      cube([wall + 4, usb_w, usb_h]);
  }
}

// Bottom-left block in panel coordinates; the others are mirrors of it.
// Top face sits against the diffuser's back, with an oval screw hole under
// the panel's corner hole.
module corner_block() {
  x0 = -clearance - wall/2; // overlaps the wall so it fuses
  size = block - x0;
  difference() {
    hull() {
      translate([x0, x0, stack_back - block_h])
        cube([size, size, block_h]);
      // 45 deg underside so it prints without support
      translate([x0, x0, stack_back - block_h - size])
        cube([0.01, 0.01, 0.01]);
    }
    translate([hole_inset, hole_inset, stack_back - screw_depth])
      scale([screw_hole[0] / screw_hole[1], 1, 1])
        cylinder(d = screw_hole[1], h = screw_depth + 0.01);
  }
}

floor_z = -(depth - floor_t);

// Cradle in local coords: board at [0..size.x, 0..size.y], clips on the -Y and
// +Y ends (open_end leaves the +Y end free), L corners locate the board.
module cradle(size, open_end = false) {
  top = board_lift + pcb_t;
  g = board_gap;
  t = cradle_wall;
  translate([0, 0, floor_z]) {
    for (end = open_end ? [0] : [0, 1]) {
      yw = end == 0 ? -g - t : size[1] + g;
      ys = end == 0 ? 0 : size[1] - 1.5;
      // Ledge under the board end
      translate([size[0]/2 - clip_w/2, ys, 0]) cube([clip_w, 1.5, board_lift]);
      // Clip wall with a lip over the board's top face
      translate([size[0]/2 - clip_w/2, yw, 0]) cube([clip_w, t, top + 0.2 + 0.8]);
      translate([size[0]/2 - clip_w/2, end == 0 ? -g : size[1] + g - clip_lip - g, top + 0.2])
        cube([clip_w, clip_lip + g, 0.8]);
    }
    if (open_end) // ledge under the USB end
      translate([size[0]/2 - clip_w/2, size[1] - 1.5, 0]) cube([clip_w, 1.5, board_lift]);
    for (cx = [0, 1], cy = [0, 1]) {
      x = cx == 0 ? -g - t : size[0] + g;
      y = cy == 0 ? -g - t : size[1] + g;
      // Arm along X (skipped on the open end), arm along Y
      if (!(open_end && cy == 1))
        translate([cx == 0 ? x : x - corner_arm + t, y, 0]) cube([corner_arm, t, top + 1]);
      translate([x, cy == 0 ? y : y - corner_arm + t, 0]) cube([t, corner_arm, top + 1]);
    }
  }
}

module electronics_mounts() {
  for (p = mcp_pos) translate(p) cradle(mcp_size);
  translate(tlc_pos) cradle(tlc_size);
  // Turn so the local +Y (USB) end faces -X
  translate([esp_pos[0] + esp_size[1], esp_pos[1], 0]) rotate(90) cradle(esp_size, open_end = true);
}

module enclosure() {
  shell();
  electronics_mounts();
  for (mx = [0, 1], my = [0, 1])
    translate([W/2, H/2, 0])
      mirror([mx, 0, 0]) mirror([0, my, 0])
        translate([-W/2, -H/2, 0])
          corner_block();
}

// Viewer stand-ins, approximate: board slabs, main IC / connector blocks
module board_at(pos, size) {
  translate([pos[0], pos[1], floor_z + board_lift]) cube([size[0], size[1], pcb_t]);
}

module pcbs() {
  for (p = mcp_pos) board_at(p, mcp_size);
  board_at(tlc_pos, tlc_size);
  board_at(esp_pos, [esp_size[1], esp_size[0]]);
}

module chips() {
  z = floor_z + board_lift + pcb_t;
  // MCP23017 SOIC-28 in the middle of each breakout
  for (p = mcp_pos)
    translate([p[0] + mcp_size[0]/2 - 3.75, p[1] + mcp_size[1]/2 - 9, z]) cube([7.5, 18, 2.5]);
  // TLC5947 and the 2-pin power terminal block
  translate([tlc_pos[0] + tlc_size[0]/2 - 3, tlc_pos[1] + tlc_size[1]/2 - 5, z]) cube([6, 10, 1.2]);
  translate([tlc_pos[0] + 13.2 - 3.5, tlc_pos[1] + 12.7 - 3.5, z]) cube([7, 7, 8]);
  // ESP32-S3 chip and the USB-C socket at the -X end
  translate([esp_pos[0] + esp_size[1] - 15, esp_pos[1] + esp_size[0]/2 - 3.5, z]) cube([7, 7, 1]);
  translate([esp_pos[0] - 0.5, esp_pos[1] + esp_size[0]/2 - 4.5, z]) cube([7.5, 9, 3.2]);
}

if (part == "pcbs") pcbs();
else if (part == "chips") chips();
else enclosure();
