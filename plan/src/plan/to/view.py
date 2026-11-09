"""SVG plot of the departure runway, takeoff distance and wind"""

import math
import re
from html import escape

from .to import FlexVSpeeds

INK = "#e6e6e6"
MUTED = "#9a9a9a"
SURFACE = "#3b3d40"
GOOD = "#3fb950"
CRITICAL = "#f85149"
SOCK = "#ff7700"
SOCK_STRIPE = "#ebf4f7"
FONT = "Arial, Helvetica, sans-serif"

WIDTH = 440
HEIGHT = 520
# Runway drawn vertically with the takeoff end at the bottom
RWY_LEFT = 40
RWY_WIDTH = 80
RWY_TOP = 20
RWY_BOTTOM = 500
RWY_CENTER = RWY_LEFT + RWY_WIDTH / 2
LABEL_X = RWY_LEFT + RWY_WIDTH + 14
# Windsock, relative to the runway so up is the takeoff direction
WIND_X = 320
WIND_Y = 80
SOCK_SCALE = 0.8
# Furthest the rotated sock reaches from its centre
SOCK_REACH = 50 * SOCK_SCALE


def opposite_runway(name: str) -> str:
    """Reciprocal runway designator, e.g. 17L -> 35R"""
    match = re.fullmatch(r"(\d{1,2})([LRC]?)", name.strip())
    if not match:
        return "?"
    number = (int(match[1]) + 17) % 36 + 1
    side = {"L": "R", "R": "L"}.get(match[2], match[2])
    return f"{number:02d}{side}"


def wind_components(
    wind_heading: float, wind_kts: float, runway_heading: float
) -> tuple[float, float]:
    """Headwind (negative is tailwind) and crosswind (negative is from the left)"""
    relative = math.radians(wind_heading - runway_heading)
    return wind_kts * math.cos(relative), wind_kts * math.sin(relative)


def _text(x, y, content, size=13, fill=INK, anchor="start", weight="normal", extra=""):
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" '
        f'fill="{fill}" text-anchor="{anchor}" font-weight="{weight}" {extra}>'
        f"{escape(str(content))}</text>"
    )


def _threshold(y: float) -> str:
    """Piano key threshold markings starting at y"""
    keys = []
    for i in range(8):
        x = RWY_LEFT + 6 + i * 9 + (6 if i >= 4 else 0)
        keys.append(f'<rect x="{x}" y="{y}" width="5" height="28" fill="{INK}"/>')
    return "".join(keys)


def _runway(takeoff: FlexVSpeeds) -> str:
    length_px = RWY_BOTTOM - RWY_TOP
    parts = [
        f'<rect x="{RWY_LEFT}" y="{RWY_TOP}" width="{RWY_WIDTH}" height="{length_px}" '
        f'fill="{SURFACE}" stroke="{INK}" stroke-width="1.5"/>',
        _threshold(RWY_BOTTOM - 36),
        _threshold(RWY_TOP + 8),
        f'<line x1="{RWY_CENTER}" y1="{RWY_TOP + 90}" x2="{RWY_CENTER}" '
        f'y2="{RWY_BOTTOM - 90}" stroke="{INK}" stroke-width="2" stroke-dasharray="14 10"/>',
        _text(RWY_CENTER, RWY_BOTTOM - 50, takeoff.runwayName, 22, anchor="middle", weight="bold"),
        _text(
            RWY_CENTER,
            RWY_TOP + 50,
            opposite_runway(takeoff.runwayName),
            22,
            anchor="middle",
            weight="bold",
            extra=f'transform="rotate(180 {RWY_CENTER} {RWY_TOP + 43})"',
        ),
        _text(
            RWY_LEFT - 12,
            (RWY_TOP + RWY_BOTTOM) / 2,
            f"{takeoff.availRunway} ft",
            12,
            MUTED,
            anchor="middle",
            extra=f'transform="rotate(-90 {RWY_LEFT - 12} {(RWY_TOP + RWY_BOTTOM) / 2})"',
        ),
    ]

    # Stop point measured from the takeoff end, clamped to the runway end
    required, available = takeoff.requiredRunway, takeoff.availRunway
    fraction = required / available if available else 1
    stop_y = RWY_BOTTOM - length_px * min(fraction, 1)
    colour = CRITICAL if takeoff.invalid else GOOD
    margin = available - required
    margin_text = f"Margin {margin} ft" if margin >= 0 else f"Short {-margin} ft"
    parts += [
        f'<line x1="{RWY_LEFT - 6}" y1="{stop_y:.1f}" x2="{RWY_LEFT + RWY_WIDTH + 6}" '
        f'y2="{stop_y:.1f}" stroke="{colour}" stroke-width="3" stroke-linecap="round"/>',
        f'<line x1="{LABEL_X - 6}" y1="{RWY_TOP}" x2="{LABEL_X - 6}" y2="{stop_y:.1f}" '
        f'stroke="{colour}" stroke-width="2" stroke-dasharray="5 4"/>',
        _text(LABEL_X, stop_y + 16, f"ASD {required} ft", 12),
    ]
    # Keep the margin label clear of the ASD label when the margin is small
    margin_y = (RWY_TOP + stop_y) / 2 + 4 if stop_y - RWY_TOP >= 40 else stop_y + 32
    parts.append(_text(LABEL_X, margin_y, margin_text, 12, MUTED))
    return "".join(parts)


def _windsock(relative_deg: float) -> str:
    """Windsock centred on the wind position, blowing downwind"""
    # Sock paths point right (+x), so rotate by 90 less than the downwind bearing
    rotation = relative_deg + 180 - 90
    return (
        f'<g transform="translate({WIND_X} {WIND_Y}) rotate({rotation:.1f}) '
        f'scale({SOCK_SCALE}) translate(-56 -30)">'
        f'<path d="M 6.255 30.174 L 36.255 6.978 C 36.255 6.978 105.466 24.103 105.526 30.088 '
        f'C 105.586 36.025 36.255 51.978 36.255 51.978 L 6.255 30.174 Z" '
        f'fill="{SOCK}" stroke="#000000" stroke-width="1.5"/>'
        f'<path d="M 36.28 7.473 L 52.878 11.761 L 53.607 47.189 L 36.21 51.438 Z" fill="{SOCK_STRIPE}"/>'
        f'<path d="M 68.164 16.054 L 84.376 20.939 L 85.226 38.663 L 68.182 43.488 Z" fill="{SOCK_STRIPE}"/>'
        "</g>"
    )


def _wind(takeoff: FlexVSpeeds) -> str:
    parts = []
    if takeoff.windVariable:
        label = f"VRB {takeoff.windKts:.0f} kt"
    elif takeoff.windKts > 0:
        parts.append(_windsock(takeoff.windHeading - takeoff.runwayHeading))
        label = f"{takeoff.windHeading:03.0f}° {takeoff.windKts:.0f} kt"
    else:
        label = "Calm"
    parts.append(_text(WIND_X, WIND_Y + SOCK_REACH + 24, label, 13, anchor="middle"))
    return "".join(parts)


def _summary(takeoff: FlexVSpeeds) -> str:
    headwind, crosswind = wind_components(
        takeoff.windHeading, takeoff.windKts, takeoff.runwayHeading
    )
    lines = [
        (f"{'Headwind' if headwind >= 0 else 'Tailwind'} {abs(headwind):.0f} kt", INK),
        (
            f"Crosswind {abs(crosswind):.0f} kt"
            + (f" from {'right' if crosswind > 0 else 'left'}" if round(crosswind) else ""),
            INK,
        ),
        (f"V1 {takeoff.v1 if takeoff.v1 > 0 else '---'}", INK),
        (f"VR {takeoff.vr}", INK),
        (f"V2 {takeoff.v2}", INK),
        (f"FLEX {takeoff.flex}" if takeoff.flex else "TOGA", INK),
    ]
    if takeoff.trim is not None:
        lines.append((f"TRIM {takeoff.trim}", INK))
    if takeoff.invalid:
        lines.append(("INVALID TAKEOFF", CRITICAL))
    y = WIND_Y + SOCK_REACH + 70
    out = []
    for content, fill in lines:
        out.append(_text(WIND_X, y, content, 14, fill, anchor="middle"))
        y += 24
    return "".join(out)


def takeoff_svg(takeoff: FlexVSpeeds) -> str:
    """Runway with takeoff distance and stop margin, plus a runway relative wind rose"""
    title = f"{takeoff.icao} runway {takeoff.runwayName} takeoff and wind"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" '
        f'width="{WIDTH}" height="{HEIGHT}" role="img">'
        f"<title>{escape(title)}</title>"
        f"{_runway(takeoff)}{_wind(takeoff)}{_summary(takeoff)}"
        "</svg>"
    )
